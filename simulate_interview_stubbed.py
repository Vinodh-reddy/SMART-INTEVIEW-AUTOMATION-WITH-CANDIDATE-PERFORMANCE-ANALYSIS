from django.test import Client
from users.models import AdminSettings, InterviewResponse
from users import views as users_views

# Stub out LLM-dependent functions to avoid external calls
users_views.generate_question = lambda messages, job_description: 'Stub question?'
users_views.evaluate_answer = lambda question, answer: {'score': 4, 'qualified': 'yes'}

# Ensure settings
AdminSettings.objects.update_or_create(id=1, defaults={'number_of_questions':2,'difficulty_level':'Medium'})

client = Client()
resp = client.post('/start/', {'name':'TC','email':'tc@example.com','job_description':'Python Developer'})
print('Start status:', resp.status_code)
print('Session keys after start:', list(client.session.keys()))
print('Max questions in session:', client.session.get('max_questions'))
print('Question count start:', client.session.get('question_count'))

# First answer
resp1 = client.post('/answer/', {'answer':'Ans 1'})
print('After 1st answer, responses count:', InterviewResponse.objects.count())
print('After 1st answer, status code:', resp1.status_code)
print('Session question_count after 1st:', client.session.get('question_count'))

# Second answer
resp2 = client.post('/answer/', {'answer':'Ans 2'})
print('After 2nd answer, responses count:', InterviewResponse.objects.count())
print('2nd response status code:', resp2.status_code)
if resp2.has_header('Location'):
    print('Redirected to:', resp2['Location'])
else:
    print('No redirect; content length:', len(resp2.content))

# Confirm interview ended (redirect to results), and that number of responses equals configured number
print('Final responses count for latest candidate:', InterviewResponse.objects.order_by('-id')[:5].count())
