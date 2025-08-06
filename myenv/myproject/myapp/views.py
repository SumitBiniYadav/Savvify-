from django.shortcuts import render, redirect
from .models import *
from gmailapi.auth import get_flow
from .models import Order, User, OrderBudget
from gmailapi.fetch import extract_orders
from googleapiclient.discovery import build
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.serializers import serialize
from django.forms.models import model_to_dict
from django.db.models import Avg, Count
from django.db.models import Sum
from datetime import datetime, timedelta
from django.utils.timezone import now as timezone_now
from django.db.models.functions import TruncDay 
from django.db.models.functions import TruncMonth, ExtractWeekDay
from django.utils.timezone import now
from collections import defaultdict
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.units import inch
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from datetime import datetime
import io
import smtplib
# Create your views here.

def index(request):
    return render(request, 'index.html')

@csrf_exempt
def signup(request):
    if request.method == 'POST':
        username = request.POST['name']
        email = request.POST['email']
        mobile = request.POST['phone']
        password = request.POST['password']
        confirm_password = request.POST['confirm_password']
        if password == confirm_password:
            user = User(username=username, email=email, mobile=mobile, password=password)
            user.save()
            return render(request, 'login.html', {'message': 'User created successfully!'})
        else: 
            return render(request, 'signup.html', {'error': 'Passwords do not match!'}) 
    else: 
        return render(request, 'signup.html')
    
@csrf_exempt
def login(request):
    if request.method == 'POST':
        email = request.POST['email']
        password = request.POST['password']
        try:
            user = User.objects.get(email=email, password=password)
            request.session['user_id'] = user.id
            request.session['profile'] = user.profile_picture.url if user.profile_picture else None
            return redirect('connect')
        except User.DoesNotExist:
            return render(request, 'login.html', {'error': 'Invalid credentials!'})
    else:
        return render(request, 'login.html')


def profile(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    # Handle POST requests (Edit Profile & Change Password)
    if request.method == 'POST':
        action = request.POST.get('action', 'edit_profile')
        
        if action == 'change_password':
            current_password = request.POST.get('current_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')
            
            # Verify current password
            if user.password != current_password:
                messages.error(request, 'Current password is incorrect!')
            elif new_password != confirm_password:
                messages.error(request, 'New passwords do not match!')
            elif len(new_password) < 6:
                messages.error(request, 'Password must be at least 6 characters long!')
            else:
                user.password = new_password
                user.save()
                messages.success(request, 'Password changed successfully!')
        
        else:  # Edit Profile
            username = request.POST.get('username')
            email = request.POST.get('email')
            mobile = request.POST.get('mobile')
            profile_picture = request.FILES.get('profile_picture')
            
            # Check for unique constraints
            try:
                # Check username uniqueness (exclude current user)
                if User.objects.filter(username=username).exclude(id=user.id).exists():
                    messages.error(request, 'Username already exists!')
                # Check email uniqueness (exclude current user)
                elif User.objects.filter(email=email).exclude(id=user.id).exists():
                    messages.error(request, 'Email already exists!')
                # Check mobile uniqueness (exclude current user)
                elif User.objects.filter(mobile=mobile).exclude(id=user.id).exists():
                    messages.error(request, 'Mobile number already exists!')
                else:
                    # Update user data
                    user.username = username
                    user.email = email
                    user.mobile = mobile
                    if profile_picture:
                        user.profile_picture = profile_picture
                    user.save()
                    messages.success(request, 'Profile updated successfully!')
            except Exception as e:
                messages.error(request, f'Error updating profile: {str(e)}')

    # Get current date for calculations
    now = timezone_now()
    
    # Calculate profile statistics
    user_orders = Order.objects.filter(user=user)
    
    # Days active (days since first order or account creation)
    first_order = user_orders.order_by('timestamp').first()
    if first_order:
        days_active = (now - first_order.timestamp).days + 1
    else:
        days_active = (now - user.created_at).days + 1
    
    # Current month orders and spending
    current_month_orders = user_orders.filter(
        timestamp__month=now.month,
        timestamp__year=now.year
    )
    current_month_spending = current_month_orders.aggregate(total=Sum('amount'))['total'] or 0
    current_month_order_count = current_month_orders.count()
    
    # Previous month for comparison
    previous_month = now.replace(day=1) - timedelta(days=1)
    previous_month_orders = user_orders.filter(
        timestamp__month=previous_month.month,
        timestamp__year=previous_month.year
    )
    previous_month_spending = previous_month_orders.aggregate(total=Sum('amount'))['total'] or 0
    
    # Calculate month-over-month change
    if previous_month_spending > 0:
        month_change_percent = ((current_month_spending - previous_month_spending) / previous_month_spending) * 100
        if month_change_percent > 0:
            month_change = f"+{month_change_percent:.1f}%"
            month_change_class = "negative"  # Spending increase is bad
        else:
            month_change = f"{month_change_percent:.1f}%"
            month_change_class = "positive"  # Spending decrease is good
    else:
        month_change = "N/A"
        month_change_class = "neutral"
    
    # Average order value
    avg_order_value = current_month_orders.aggregate(avg=Avg('amount'))['avg'] or 0
    
    # Average weekly spending (current month)
    weeks_in_month = now.day // 7 + 1
    avg_weekly_spending = current_month_spending / weeks_in_month if weeks_in_month > 0 else 0
    
    # Budget streak calculation
    current_budget = OrderBudget.objects.filter(user=user).order_by('-created_at').first()
    if current_budget and current_budget.monthly_budget > 0:
        # Simple streak: days user stayed within daily budget this month
        daily_budget = current_budget.monthly_budget / 30  # Rough daily budget
        streak_days = 0
        
        # Check each day of current month
        for day in range(1, now.day + 1):
            day_date = now.replace(day=day)
            day_spending = user_orders.filter(
                timestamp__date=day_date.date()
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            if day_spending <= daily_budget:
                streak_days += 1
            else:
                streak_days = 0  # Reset streak
        
        current_streak = streak_days
    else:
        current_streak = 0
    
    # Top platforms this month
    top_platforms = current_month_orders.values('platform').annotate(
        total_amount=Sum('amount'),
        order_count=Count('id')
    ).order_by('-total_amount')[:5]
    
    # Total saved calculation (example: difference from a baseline or budget savings)
    total_orders_value = user_orders.aggregate(total=Sum('amount'))['total'] or 0
    # Assuming users save by not overspending their budget
    if current_budget:
        months_active = max(1, days_active // 30)
        potential_spending = current_budget.monthly_budget * months_active
        total_saved = max(0, potential_spending - total_orders_value)
    else:
        # Default saving calculation (10% of total spending as hypothetical savings)
        total_saved = total_orders_value * 0.1
    
    context = {
        'user': user,
        'days_active': days_active,
        'total_saved': total_saved,
        'current_month_spending': current_month_spending,
        'current_month_orders': current_month_order_count,
        'month_change': month_change,
        'month_change_class': month_change_class,
        'avg_order_value': avg_order_value,
        'avg_weekly_spending': avg_weekly_spending,
        'current_streak': current_streak,
        'top_platforms': top_platforms,
    }
    
    return render(request, 'profile.html', context)
    

def connect_gmail(request):
    flow = get_flow()
    auth_url, _ = flow.authorization_url(prompt='consent')
    return redirect(auth_url)

def oauth2callback(request):
    flow = get_flow()
    flow.fetch_token(authorization_response=request.build_absolute_uri())

    credentials = flow.credentials
    print("✅ Gmail OAuth Success")
    print("Access Token:", credentials.token)

    request.session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

    return redirect('home')


@csrf_exempt
def save_orders(request):
    if not request.session.get('credentials'):
        return JsonResponse({'success': False, 'message': 'Gmail not connected'}, status=401)

    user_id = request.session.get('user_id')
    if not user_id:
        return JsonResponse({'success': False, 'message': 'User not logged in'}, status=401)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'}, status=404)

    orders_before = Order.objects.filter(user=user).count()
    extract_orders(request.session, user)
    orders_after = Order.objects.filter(user=user).count()

    new_orders = Order.objects.filter(user=user).order_by('-timestamp')[:orders_after - orders_before]
    new_orders_serialized = [
        {
            "platform": o.platform,
            "order_number": o.order_number,
            "amount": o.amount,
        } for o in new_orders
    ]

    return JsonResponse({
        'success': True,
        'count': len(new_orders_serialized),
        'orders': new_orders_serialized,
        'total_orders': orders_after
    })

def home(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return render(request, 'home.html')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    orders = Order.objects.filter(user=user).order_by('-timestamp')[:10]

    now = timezone_now()

    current_month_orders = Order.objects.filter(
        user=user,
        timestamp__month=now.month,
        timestamp__year=now.year
    )

    total_spent = current_month_orders.aggregate(total=Sum('amount'))['total'] or 0

    app_spending = current_month_orders.values('platform').annotate(
        total_amount=Sum('amount'),
        order_count=Count('id')
    ).order_by('-total_amount')

    # === Average Order Value ===
    avg_order_value = current_month_orders.aggregate(avg=Avg('amount'))['avg'] or 0
    avg_order_value = round(avg_order_value, 2)

    # === Most Active Day ===
    day_orders = current_month_orders.annotate(day=TruncDay('timestamp')).values('day').annotate(order_count=Count('id')).order_by('-order_count')
    most_active_day = day_orders[0]['day'].strftime('%A') if day_orders else 'N/A'
    most_active_day_orders = day_orders[0]['order_count'] if day_orders else 0

    # === Budget Logic ===
    current_budget = OrderBudget.objects.filter(user=user).order_by('-created_at').first()
    monthly_budget = current_budget.monthly_budget if current_budget else 0

    budget_percentage = round((total_spent / monthly_budget) * 100, 1) if monthly_budget else 0
    budget_progress_deg = round((budget_percentage / 100) * 360, 1)

    if not monthly_budget:
        budget_status = "No Budget Set"
        budget_status_class = "on-track"
    elif budget_percentage < 70:
        budget_status = "You're on track!"
        budget_status_class = "on-track"
    elif 70 <= budget_percentage < 100:
        budget_status = "Caution: High spending"
        budget_status_class = "warning"
    else:
        budget_status = "Over Budget!"
        budget_status_class = "danger"

    last_day = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    days_remaining = (last_day - now).days

    # === Smart Insights ===
    alerts = []

    if monthly_budget and budget_percentage > 100:
        alerts.append({
            'type': 'danger',
            'title': 'Overspending Alert!',
            'message': f"You’ve spent ₹{total_spent} this month, which is over your budget of ₹{monthly_budget}."
        })
    elif 70 <= budget_percentage <= 100:
        alerts.append({
            'type': 'warning',
            'title': 'Caution: Approaching Budget Limit',
            'message': f"You’ve used {budget_percentage}% of your monthly budget. Be careful with further spending."
        })

    largest_order = current_month_orders.order_by('-amount').first()
    if largest_order and largest_order.amount > 1000:
        alerts.append({
            'type': 'info',
            'title': 'High-value Order Detected',
            'message': f"Your largest order this month was ₹{largest_order.amount} on {largest_order.timestamp.strftime('%B %d')}."
        })

    if current_month_orders.count() == 0:
        alerts.append({
            'type': 'info',
            'title': 'No Orders This Month',
            'message': "You haven't placed any orders yet this month. That’s some serious saving!"
        })

    if app_spending:
        top_platform = app_spending[0]
        if top_platform['order_count'] > 5:
            alerts.append({
                'type': 'info',
                'title': f"Frequent usage of {top_platform['platform']}",
                'message': f"You’ve ordered {top_platform['order_count']} times from {top_platform['platform']} this month. Maybe try something new?"
            })

    return render(request, 'home.html', {
        'user': user,
        'orders': orders,
        'total_spent': total_spent,
        'app_spending': app_spending,
        'current_month': now.strftime('%B %Y'),
        'monthly_budget': monthly_budget,
        'budget_percentage': budget_percentage,
        'budget_progress_deg': budget_progress_deg,
        'budget_status': budget_status,
        'budget_status_class': budget_status_class,
        'days_remaining': days_remaining,
        'avg_order_value': avg_order_value,
        'most_active_day': most_active_day,
        'most_active_day_orders': most_active_day_orders,
        'alerts': alerts,
    })



def connect(request):
    return render(request, 'connect.html')

def logout(request):
    request.session.flush() 
    return redirect('login')

def intro(request):
    return render(request, 'intro.html')

def reports(request, pk):
    try:
        user = User.objects.get(id=pk)
        orders = Order.objects.filter(user=user).order_by('-timestamp')

        total_spent = orders.aggregate(total=Sum('amount'))['total'] or 0
        total_orders = orders.count()
        avg_order = orders.aggregate(avg=Avg('amount'))['avg'] or 0

        # Platform stats
        platform_stats = orders.values('platform').annotate(
            orders=Count('id'),
            total=Sum('amount'),
            average=Avg('amount')
        )

        for p in platform_stats:
            p['name'] = p['platform'].capitalize()

        platforms_used = platform_stats.count()

        # === Spending Trends: last 6 months ===
        monthly_data = (
            orders.annotate(month=TruncMonth('timestamp'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )
        spending_trends = [{'month': m['month'].strftime('%b'), 'total': m['total']} for m in monthly_data]

        # === Platform Distribution ===
        platform_distribution = [
            {'platform': p['platform'], 'total': p['total']} for p in platform_stats
        ]

        # === Monthly Comparison ===
        now_date = now()
        current_month = orders.filter(timestamp__month=now_date.month, timestamp__year=now_date.year)
        last_month = orders.filter(
            timestamp__month=(now_date.month - 1 or 12),
            timestamp__year=(now_date.year if now_date.month > 1 else now_date.year - 1)
        )
        last_3_months = orders.filter(timestamp__gte=now_date - timedelta(days=90))

        comparison = {
            'current': current_month.aggregate(total=Sum('amount'))['total'] or 0,
            'last': last_month.aggregate(total=Sum('amount'))['total'] or 0,
            'avg_3m': round((last_3_months.aggregate(total=Sum('amount'))['total'] or 0) / 3, 2)
        }

        # === Order Frequency: by day of week ===
        weekday_map = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        frequency_raw = (
            orders.annotate(day=ExtractWeekDay('timestamp'))
            .values('day')
            .annotate(count=Count('id'))
        )
        order_frequency = {weekday_map[item['day'] - 1]: item['count'] for item in frequency_raw}

        # === Key Metrics Change Calculations ===
        prev_month = now_date.replace(day=1) - timedelta(days=1)

        current_month_orders = orders.filter(timestamp__month=now_date.month, timestamp__year=now_date.year)
        last_month_orders = orders.filter(timestamp__month=prev_month.month, timestamp__year=prev_month.year)

        # Total Spent Change
        spent_current = current_month_orders.aggregate(total=Sum('amount'))['total'] or 0
        spent_last = last_month_orders.aggregate(total=Sum('amount'))['total'] or 0
        spent_change = ((spent_current - spent_last) / spent_last * 100) if spent_last else 0
        spent_class = 'positive' if spent_change < 0 else 'negative'

        # Total Orders Change
        orders_current = current_month_orders.count()
        orders_last = last_month_orders.count()
        order_change = ((orders_current - orders_last) / orders_last * 100) if orders_last else 0
        order_class = 'positive' if order_change >= 0 else 'negative'

        # Avg Order Value Change
        avg_current = current_month_orders.aggregate(avg=Avg('amount'))['avg'] or 0
        avg_last = last_month_orders.aggregate(avg=Avg('amount'))['avg'] or 0
        avg_change = ((avg_current - avg_last) / avg_last * 100) if avg_last else 0
        avg_class = 'positive' if avg_change >= 0 else 'negative'

        return render(request, 'reports.html', {
            'user': user,
            'orders': orders,
            'total_spent': total_spent,
            'total_orders': total_orders,
            'avg_order': round(avg_order, 2),
            'platforms_used': platforms_used,
            'platform_stats': platform_stats,
            'spending_trends': spending_trends,
            'platform_distribution': platform_distribution,
            'monthly_comparison': comparison,
            'order_frequency': order_frequency,

            # Metrics changes
            'real_spent_change': f"{spent_change:+.1f}%",
            'spent_change_class': spent_class,
            'real_order_change': f"{order_change:+.1f}%",
            'order_change_class': order_class,
            'real_avg_change': f"{avg_change:+.1f}%",
            'avg_change_class': avg_class,
        })

    except User.DoesNotExist:
        return render(request, 'reports.html', {'error': "User not found"})


def contact(request):
    return render(request, 'contact.html')


def set_budget(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    # Get latest budget entry
    current_budget = OrderBudget.objects.filter(user=user).order_by('-created_at').first()

    # Orders this month
    now = datetime.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    orders_this_month = Order.objects.filter(user=user, timestamp__gte=start_of_month)
    spent_this_month = orders_this_month.aggregate(total=Sum('amount'))['total'] or 0

    remaining_budget = current_budget.monthly_budget - spent_this_month if current_budget else 0
    budget_progress = (spent_this_month / current_budget.monthly_budget * 100) if current_budget and current_budget.monthly_budget else 0

    if request.method == 'POST':
        try:
            amount = float(request.POST.get('monthly_budget'))
            if amount < 100:
                return render(request, 'budget.html', {
                    'user': user,
                    'current_budget': current_budget,
                    'spent_this_month': spent_this_month,
                    'remaining_budget': remaining_budget,
                    'budget_progress': round(budget_progress, 1),
                    'messages': [{'tags': 'error', 'message': 'Budget must be at least ₹100'}]
                })

            if current_budget:
                current_budget.monthly_budget = amount
                current_budget.save()
                success_message = 'Monthly budget updated successfully.'
            else:
                OrderBudget.objects.create(user=user, monthly_budget=amount)
                success_message = 'Monthly budget set successfully.'

            return render(request, 'budget.html', {
                'user': user,
                'current_budget': OrderBudget.objects.filter(user=user).order_by('-created_at').first(),
                'spent_this_month': spent_this_month,
                'remaining_budget': remaining_budget,
                'budget_progress': round(budget_progress, 1),
                'messages': [{'tags': 'success', 'message': success_message}]
            })

        except Exception as e:
            return render(request, 'budget.html', {
                'user': user,
                'current_budget': current_budget,
                'spent_this_month': spent_this_month,
                'remaining_budget': remaining_budget,
                'budget_progress': round(budget_progress, 1),
                'messages': [{'tags': 'error', 'message': str(e)}]
            })

    return render(request, 'budget.html', {
        'user': user,
        'current_budget': current_budget,
        'spent_this_month': spent_this_month,
        'remaining_budget': remaining_budget,
        'budget_progress': round(budget_progress, 1)
    })


def hcontact(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    return render(request, 'hcontact.html', {'user': user})

def export_user_data(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    # Create the HttpResponse with PDF headers
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="savvify_user_report.pdf"'

    # Create PDF buffer
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Define colors
    primary_color = HexColor('#2563eb')  # Blue
    secondary_color = HexColor('#f1f5f9')  # Light gray
    accent_color = HexColor('#059669')  # Green
    text_color = HexColor('#1f2937')  # Dark gray
    
    def draw_header():
        # Header background
        p.setFillColor(primary_color)
        p.rect(0, height - 100, width, 100, fill=1, stroke=0)
        
        # Company logo/title
        p.setFillColor(white)
        p.setFont("Helvetica-Bold", 24)
        p.drawString(50, height - 45, "SAVVIFY")
        
        p.setFont("Helvetica", 12)
        p.drawString(50, height - 65, "User Data Export Report")
        
        # Date
        p.setFont("Helvetica", 10)
        current_date = datetime.now().strftime("%B %d, %Y")
        p.drawRightString(width - 50, height - 45, f"Generated on: {current_date}")
        
        return height - 120
    
    def draw_user_info_card(y_pos):
        # User info card background
        p.setFillColor(secondary_color)
        p.rect(40, y_pos - 120, width - 80, 100, fill=1, stroke=0)
        
        # Card border
        p.setStrokeColor(primary_color)
        p.setLineWidth(2)
        p.rect(40, y_pos - 120, width - 80, 100, fill=0, stroke=1)
        
        # User info title
        p.setFillColor(primary_color)
        p.setFont("Helvetica-Bold", 14)
        p.drawString(60, y_pos - 35, "USER INFORMATION")
        
        # User details
        p.setFillColor(text_color)
        p.setFont("Helvetica", 11)
        p.drawString(60, y_pos - 55, f"Name: {user.username}")
        p.drawString(60, y_pos - 75, f"Email: {user.email}")
        p.drawString(60, y_pos - 95, f"Mobile: {user.mobile}")
        
        # Add icon-like elements (simple geometric shapes)
        p.setFillColor(accent_color)
        # User icon
        p.circle(width - 100, y_pos - 70, 15, fill=1, stroke=0)
        p.setFillColor(white)
        p.circle(width - 100, y_pos - 70, 12, fill=1, stroke=0)
        
        return y_pos - 140
    
    def draw_orders_section(y_pos):
        orders = Order.objects.filter(user=user).order_by('-timestamp')
        
        if not orders.exists():
            p.setFillColor(text_color)
            p.setFont("Helvetica", 12)
            p.drawString(50, y_pos, "No orders found.")
            return y_pos - 30
        
        # Orders section title
        p.setFillColor(primary_color)
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, y_pos, "RECENT ORDERS")
        
        # Subtitle
        p.setFillColor(text_color)
        p.setFont("Helvetica", 10)
        total_orders = orders.count()
        showing_orders = min(25, total_orders)
        p.drawString(50, y_pos - 20, f"Showing {showing_orders} of {total_orders} orders")
        
        y_pos -= 50
        
        # Table headers
        headers = ["Date", "Platform", "Amount", "Order #", "Status"]
        
        # Draw header row background
        p.setFillColor(primary_color)
        p.rect(40, y_pos - 25, width - 80, 20, fill=1, stroke=0)
        
        # Draw header text
        p.setFillColor(white)
        p.setFont("Helvetica-Bold", 10)
        col_widths = [80, 100, 80, 120, 80]
        col_positions = [50, 130, 230, 310, 430]
        
        for i, header in enumerate(headers):
            p.drawString(col_positions[i], y_pos - 15, header)
        
        y_pos -= 35
        
        # Draw orders
        p.setFont("Helvetica", 9)
        row_count = 0
        
        for order in orders[:25]:  # Limit to top 25
            if y_pos < 100:  # Start new page if needed
                p.showPage()
                y_pos = draw_header()
                
                # Redraw table headers on new page
                p.setFillColor(primary_color)
                p.rect(40, y_pos - 25, width - 80, 20, fill=1, stroke=0)
                
                p.setFillColor(white)
                p.setFont("Helvetica-Bold", 10)
                for i, header in enumerate(headers):
                    p.drawString(col_positions[i], y_pos - 15, header)
                
                y_pos -= 35
                p.setFont("Helvetica", 9)
            
            # Alternate row colors
            if row_count % 2 == 0:
                p.setFillColor(HexColor('#f8fafc'))
                p.rect(40, y_pos - 20, width - 80, 16, fill=1, stroke=0)
            
            # Draw row data
            p.setFillColor(text_color)
            
            # Format date
            date_str = order.timestamp.strftime('%d/%m/%Y')
            p.drawString(col_positions[0], y_pos - 12, date_str)
            
            # Platform (truncate if too long)
            platform = order.platform[:12] + "..." if len(order.platform) > 12 else order.platform
            p.drawString(col_positions[1], y_pos - 12, platform)
            
            # Amount with Rs prefix
            amount_str = f"Rs {order.amount:,.2f}"
            p.drawString(col_positions[2], y_pos - 12, amount_str)
            
            # Order number (truncate if too long)
            order_num = str(order.order_number)[:15] + "..." if len(str(order.order_number)) > 15 else str(order.order_number)
            p.drawString(col_positions[3], y_pos - 12, order_num)
            
            # Status (if available)
            status = getattr(order, 'status', 'Completed')
            p.drawString(col_positions[4], y_pos - 12, status)
            
            y_pos -= 20
            row_count += 1
        
        return y_pos
    
    def draw_summary_card(y_pos):
        orders = Order.objects.filter(user=user)
        total_amount = sum(order.amount for order in orders)
        total_orders = orders.count()
        
        if y_pos < 150:
            p.showPage()
            y_pos = height - 50
        
        # Summary card
        p.setFillColor(accent_color)
        p.rect(40, y_pos - 80, width - 80, 60, fill=1, stroke=0)
        
        p.setFillColor(white)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(60, y_pos - 30, "ORDER SUMMARY")
        
        p.setFont("Helvetica", 10)
        p.drawString(60, y_pos - 50, f"Total Orders: {total_orders}")
        p.drawString(60, y_pos - 65, f"Total Amount: Rs {total_amount:,.2f}")
        
        return y_pos - 100
    
    def draw_footer(y_pos):
        # Footer line
        p.setStrokeColor(primary_color)
        p.setLineWidth(1)
        p.line(50, 50, width - 50, 50)
        
        # Footer text
        p.setFillColor(text_color)
        p.setFont("Helvetica", 8)
        p.drawString(50, 35, "This report is confidential and generated for authorized use only.")
        p.drawRightString(width - 50, 35, "Savvify - Smart Shopping Platform")
    
    # Draw PDF content
    current_y = draw_header()
    current_y = draw_user_info_card(current_y)
    current_y = draw_orders_section(current_y)
    current_y = draw_summary_card(current_y)
    draw_footer(current_y)
    
    # Finalize PDF
    p.showPage()
    p.save()
    
    # Get PDF data and return response
    pdf_data = buffer.getvalue()
    buffer.close()
    response.write(pdf_data)
    
    return response


def insights(request):
    try: 
        user = User.objects.get(id=request.session.get('user_id'))
        return render(request, 'insights.html', {'user': user})
    except:
        return redirect('login')
    

def moto(request):
    try:
        user = User.objects.get(id=request.session.get('user_id'))
        return render(request, 'moto.html', {'user': user})
    except User.DoesNotExist:
        return redirect('login')
    

