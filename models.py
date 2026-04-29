from django.db import models

# =========================
# Candidate Model
# =========================
class Candidate(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    job_description = models.TextField()

    def __str__(self):
        return self.name


# =========================
# Interview Responses
# =========================
# class InterviewResponse(models.Model):
#     candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE)
#     question = models.TextField()
#     answer = models.TextField()
#     score = models.IntegerField(null=True, blank=True)

#     def __str__(self):
#         return f"{self.candidate.name} - Score: {self.score}"

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator

class InterviewResponse(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField()
    score = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)  # ✅ ADD THIS


# =========================
# Registered Users (Admin/User Login)
# =========================
class RegisteredUser(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    mobile = models.CharField(max_length=15)
    password = models.CharField(max_length=100)  # Plain for demo (hash in prod)
    image = models.ImageField(upload_to='user_images/')
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return self.name


# =========================
# Interview Settings (ADMIN CONTROLS LEVEL)
# =========================
class InterviewSettings(models.Model):
    LEVEL_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    question_level = models.CharField(
        max_length=10,
        choices=LEVEL_CHOICES,
        default='easy'
    )

    def __str__(self):
        return f"Question Level: {self.question_level}"

class AdminSettings(models.Model):
    difficulty_level = models.CharField(max_length=20, default='Easy', choices=[
        ('Easy', 'Easy'),
        ('Medium', 'Medium'),
        ('Hard', 'Hard')
    ])
    number_of_questions = models.IntegerField(default=10, validators=[MinValueValidator(1)])
    question_type = models.CharField(max_length=20, default='Descriptive', choices=[
        ('MCQ', 'MCQ'),
        ('Descriptive', 'Descriptive'),
        ('Coding', 'Coding'),
        ('Voice', 'Voice')
    ])
    interview_date = models.DateTimeField(default=timezone.now)
    duration = models.IntegerField(default=60)  # minutes
    evaluation_weightage = models.JSONField(default=dict)  # e.g. {'accuracy': 0.4, 'fluency': 0.3, ...}
    enable_emotion_analysis = models.BooleanField(default=True)
    enable_voice_interview = models.BooleanField(default=True)
    # Motion detection / proctoring settings
    enable_motion_detection = models.BooleanField(default=True)
    motion_pixel_threshold = models.IntegerField(default=30)
    motion_ratio_threshold = models.FloatField(default=0.02)
    motion_window_seconds = models.IntegerField(default=45)
    motion_window_count = models.IntegerField(default=2)
    motion_sample_interval_ms = models.IntegerField(default=800)

    # Admin interests: allow admin to suggest focus topics and allow varied question types
    focus_topics = models.TextField(blank=True, default='', help_text='Comma-separated topics or skills to focus questions on, e.g. "Python, SQL, algorithms"')
    allow_varied_question_types = models.BooleanField(default=False, help_text='If enabled, the system may generate different question types (MCQ/Coding/Descriptive) based on role.')


# Server-side log of motion events (for audit and rule evaluation)
class MotionEvent(models.Model):
    candidate = models.ForeignKey(Candidate, null=True, blank=True, on_delete=models.SET_NULL)
    ratio = models.FloatField()
    created_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)

    def __str__(self):
        if self.candidate:
            return f"MotionEvent {self.id} - {self.candidate.name} - {self.ratio}"
        return f"MotionEvent {self.id} - {self.ratio}"