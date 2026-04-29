from django import forms
from .models import AdminSettings

# forms.py
class CandidateForm(forms.Form):
    name = forms.CharField(max_length=100)
    email = forms.EmailField(widget=forms.EmailInput(attrs={'placeholder': 'enter valid email to send result'}))
    job_description = forms.CharField(widget=forms.Textarea(attrs={'placeholder': 'Example :Python Developer'}))


class AnswerForm(forms.Form):
    answer = forms.CharField(widget=forms.Textarea)


class AdminSettingsForm(forms.ModelForm):
    class Meta:
        model = AdminSettings
        fields = [
            'difficulty_level', 'number_of_questions', 'question_type', 'interview_date', 'duration', 'evaluation_weightage',
            'enable_emotion_analysis', 'enable_voice_interview',
            # Motion settings
            'enable_motion_detection', 'motion_pixel_threshold', 'motion_ratio_threshold', 'motion_window_seconds', 'motion_window_count', 'motion_sample_interval_ms',
            # Admin interest / question variety
            'focus_topics', 'allow_varied_question_types'
        ]
        widgets = {
            'interview_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'evaluation_weightage': forms.Textarea(attrs={'placeholder': '{"accuracy": 0.4, "fluency": 0.3, "emotion_stability": 0.2, "eye_contact": 0.1}'}),
            'focus_topics': forms.Textarea(attrs={'placeholder': 'Comma-separated topics, e.g. "Python, SQL, algorithms"'}),
        }

    def clean_number_of_questions(self):
        n = self.cleaned_data.get('number_of_questions')
        if n is None or n <= 0:
            raise forms.ValidationError('Number of questions must be a positive integer.')
        return n
