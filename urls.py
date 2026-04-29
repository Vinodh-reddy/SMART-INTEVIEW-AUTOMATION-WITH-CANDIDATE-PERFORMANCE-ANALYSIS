"""
URL configuration for AI_Interviewer project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
import importlib

def _lazy_view(view_name):
    def _wrapped(request, *args, **kwargs):
        module = importlib.import_module('users.views')
        view = getattr(module, view_name)
        return view(request, *args, **kwargs)
    return _wrapped


urlpatterns = [
    path('admin/', admin.site.urls),
    path("", _lazy_view('index'), name="index"),
    path('home/', _lazy_view('home'), name='home'),
    path('register/', _lazy_view('register_view'), name='register'),
    path('user-login/', _lazy_view('user_login'), name='user_login'),
    path('user-homepage/', _lazy_view('user_homepage'), name='user_homepage'),  # new user homepage url
    path('admin-login/', _lazy_view('admin_login'), name='admin_login'),
    path('admin-home/', _lazy_view('admin_home'), name='admin_home'),
    path('admin_settings/', _lazy_view('admin_settings'), name='admin_settings'),

    path('admin-dashboard/', _lazy_view('admin_dashboard'), name='admin_dashboard'),
    path('activate/<int:user_id>/', _lazy_view('activate_user'), name='activate_user'),
    path('deactivate/<int:user_id>/', _lazy_view('deactivate_user'), name='deactivate_user'),
    path('delete/<int:user_id>/', _lazy_view('delete_user'), name='delete_user'),
    path('delete-candidate/<int:candidate_id>/', _lazy_view('delete_candidate'), name='delete_candidate'),
    path('delete-candidates/', _lazy_view('delete_candidates'), name='delete_candidates'),
    path('user-logout/', _lazy_view('user_logout'), name='user_logout'),
    path("forgot-password/", _lazy_view('forgot_password'), name="forgot_password"),
    path("verify-otp/", _lazy_view('verify_otp'), name="verify_otp"),
    path("reset-password/", _lazy_view('reset_password'), name="reset_password"),
    path('start/', _lazy_view('start_interview'), name='start_interview'),
    path('answer/', _lazy_view('answer_question'), name='answer_question'),
    path('results/all/', _lazy_view('all_results'), name='all_results'),  # <-- Add this
    path('results/<int:candidate_id>/', _lazy_view('interview_results'), name='interview_results'),
    path('tab_violation/', _lazy_view('tab_violation'), name="tab_violation"),
    path('vision-analyze/', _lazy_view('vision_analyze'), name='vision_analyze'),
    path('motion-event/', _lazy_view('motion_event'), name='motion_event'),


]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
