from django.test import Client
c = Client()
resp = c.post('/admin_settings/', {
    'difficulty_level': 'Medium',
    'number_of_questions': '2',
    'question_type': 'Descriptive',
    'interview_date': '2026-01-31T10:00',
    'duration': '60',
    'evaluation_weightage': '{}',
    'enable_emotion_analysis': 'on',
    'enable_voice_interview': 'on'
}, follow=True)
print('Status:', resp.status_code)
content = resp.content.decode('utf-8')
# Print small parts
print('Contains success message:', 'Settings saved successfully!' in content)
# Find messages block
if '<div class="mb-4">' in content:
    start = content.find('<div class="mb-4">')
    print('Messages block snippet:\n', content[start:start+200])
else:
    print('No messages block in HTML')
# Show current settings area
if 'Number of Questions:' in content:
    i = content.find('Number of Questions:')
    print('Current settings snippet:\n', content[i-60:i+120])
else:
    print('Number of Questions not present')
# Save full content to temp file for manual inspection if needed
open('tests/admin_settings_response.html', 'w', encoding='utf-8').write(content)
print('\nFull response saved to tests/admin_settings_response.html')
