from . import views
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('index/', views.index, name='index'),  # Maps the root URL to the index view
    path('signup/', views.signup, name='signup'),  # Maps the signup URL to the signup view
    path('login/', views.login, name='login'),  # Maps the login URL to the login view
    path('home/', views.home, name='home'),  # Maps the home URL to the home view
    path('profile/', views.profile, name='profile'),  # Maps the profile URL to the profile view
    path('logout/', views.logout, name='logout'),  # Maps the logout URL to the logout view
    path('connect-gmail/', views.connect_gmail, name='connect_gmail'), # Maps the connect_gmail URL to the connect_gmail view
    path('oauth2callback/', views.oauth2callback, name='oauth2callback'), # Maps the OAuth2 callback URL to the oauth2callback view
    path('connect/', views.connect, name='connect'),  # Maps the connect URL to the connect view
    path('fetch-orders/', views.save_orders, name='save_orders'), # Maps the fetch-orders URL to the save_orders view
    path('intro/', views.intro, name='intro'),  # Maps the check URL to the check view
    path('reports/<int:pk>', views.reports, name='reports'),  # Maps the reports URL to the reports view
    path('contact/', views.contact, name='contact'),  # Maps the set-budget URL to the set_budget view
    path('budget/', views.set_budget, name='set-budget'),  # Maps the set-budget URL to the set_budget view
    path('hcontact/', views.hcontact, name='hcontact'),  # Maps the hcontact URL to the hcontact view
    path('export/', views.export_user_data, name='export_data'), # Maps the export URL to the export_user_data view
    path('insights/', views.insights, name='insights'),  # Maps the insights URL to the insights view
    path('moto/', views.moto, name='moto'),  # Maps the moto URL to the moto view
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)