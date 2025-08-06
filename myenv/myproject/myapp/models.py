from django.db import models

# Create your models here.


class User(models.Model):
    
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    mobile = models.CharField(max_length=15, unique=True)
    password = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)

    def __str__(self):
        return self.username
    

class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    platform = models.CharField(max_length=50)
    order_number = models.CharField(max_length=100, unique=True)
    amount = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.platform} | ₹{self.amount} | {self.order_number or 'N/A'}"
    

class OrderBudget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    monthly_budget = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} | ₹{self.monthly_budget} | {self.created_at.strftime('%Y-%m-%d')}"