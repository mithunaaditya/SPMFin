from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets, permissions, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Account, Category, Transaction, Budget
from .serializers import AccountSerializer, CategorySerializer, TransactionSerializer, BudgetSerializer, RegisterSerializer
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django_filters.rest_framework import DjangoFilterBackend

class IsOwnerMixin:
    """
    Simple mixin to restrict queryset to authenticated user's objects.
    Each viewset must set queryset and serializer_class.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        return qs.filter(user=user)

class AccountViewSet(IsOwnerMixin, viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    filter_backends = [OrderingFilter, SearchFilter]
    search_fields = ['name']

class CategoryViewSet(IsOwnerMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    filter_backends = [OrderingFilter, SearchFilter]
    search_fields = ['name']

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class TransactionViewSet(IsOwnerMixin, viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related('account','category').all()
    serializer_class = TransactionSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ['account','category','txn_date']
    search_fields = ['description','location']

    def get_queryset(self):
        user = self.request.user
        queryset = Transaction.objects.filter(user=user)

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(txn_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(txn_date__lte=end_date)

        return queryset
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class BudgetViewSet(IsOwnerMixin, viewsets.ModelViewSet):
    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['category','account','period_start','period_end']

# Register new user
class RegisterView(generics.CreateAPIView):
    """
    Allows new users to register.
    Automatically creates an auth token on registration.
    """
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        user = User.objects.get(username=response.data["username"])
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "token": token.key
        })


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """
    Authenticate an existing user and return their token.
    """
    from django.contrib.auth import authenticate
    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return Response({"error": "Username and password required"}, status=400)

    user = authenticate(username=username, password=password)
    if user:
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "token": token.key
        })
    else:
        return Response({"error": "Invalid credentials"}, status=400)
