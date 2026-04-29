from django.test import Client
from users.models import AdminSettings, InterviewResponse

# Ensure settings
AdminSettings.objects.update_or_create(id=1, defaults={'number_of_questions':2,'difficulty_level':'Medium'})

client = Client()
resp = client.post('/start/', {'name':'TC','email':'tc@example.com','job_description':'Python Developer'})
session = client.session
print('Session keys after start:', list(session.keys()))
print('Max questions in session:', session.get('max_questions'))
print('Question count start:', session.get('question_count'))

# First answer
resp1 = client.post('/answer/', {'answer':'Ans 1'})
print('After 1st answer, responses count:', InterviewResponse.objects.count())
print('Session question_count:', client.session.get('question_count'))

# Second answer
resp2 = client.post('/answer/', {'answer':'Ans 2'})
print('After 2nd answer, responses count:', InterviewResponse.objects.count())
print('2nd response status code:', resp2.status_code)

# Print last redirect target when available
if resp2.has_header('Location'):
    print('Redirected to:', resp2['Location'])
else:
    print('No redirect header in response 2')

# Show saved responses
for r in InterviewResponse.objects.all():
    print(r.candidate.name, r.question, r.answer, r.score)
