from django.contrib import admin
from .models import Candidate, InterviewResponse, RegisteredUser, AdminSettings, MotionEvent

@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'job_description')
    search_fields = ('name', 'email', 'job_description')


@admin.register(InterviewResponse)
class InterviewResponseAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'question', 'answer', 'score', 'created_at')
    search_fields = ('candidate__name', 'question', 'answer')
    list_filter = ('score',)


@admin.register(RegisteredUser)
class RegisteredUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'mobile', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'email', 'mobile')


@admin.register(AdminSettings)
class AdminSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'difficulty_level', 'number_of_questions', 'question_type', 'duration', 'enable_emotion_analysis', 'enable_voice_interview', 'enable_motion_detection', 'allow_varied_question_types'
    )
    search_fields = ('difficulty_level', 'question_type')
    fieldsets = (
        (None, {
            'fields': ('difficulty_level', 'number_of_questions', 'question_type', 'duration', 'interview_date', 'evaluation_weightage')
        }),
        ('Toggles', {
            'fields': ('enable_emotion_analysis', 'enable_voice_interview', 'allow_varied_question_types', 'enable_motion_detection')
        }),
        ('Motion Settings', {
            'fields': ('motion_pixel_threshold', 'motion_ratio_threshold', 'motion_window_seconds', 'motion_window_count', 'motion_sample_interval_ms')
        }),
        ('Admin Interests', {
            'fields': ('focus_topics',)
        }),
    )


@admin.register(MotionEvent)
class MotionEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'ratio', 'created_at', 'note')
    list_filter = ('created_at', 'candidate')
    search_fields = ('candidate__name', 'note')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
