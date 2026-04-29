import json
import re
import random
import pytz

from django.conf import settings
from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from django.contrib import messages
from django.db.models import Max
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage


from .forms import CandidateForm, AnswerForm, AdminSettingsForm
from .models import (
    Candidate,
    InterviewResponse,
    RegisteredUser,
    InterviewSettings,
    AdminSettings,
    MotionEvent
)
from django.http import JsonResponse
# ===================== LLM CONFIG =====================

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=0.7,
)

# ===================== QUESTION GENERATION =====================

def generate_question(messages, job_description):
    # Use AdminSettings (single source of truth) for difficulty level
    settings_obj = AdminSettings.objects.first()
    level = settings_obj.difficulty_level if settings_obj else "Easy"

    # incorporate admin-configured focus topics and variety
    focus = (settings_obj.focus_topics or '').strip() if settings_obj else ''
    allow_varied = settings_obj.allow_varied_question_types if settings_obj else False
    preferred_type = settings_obj.question_type if settings_obj else 'Descriptive'

    types_note = ''
    if allow_varied:
        types_note = (
            "If appropriate for the role, you MAY select any of these question types: [MCQ], [CODING], [DESCRIPTIVE]. "
            "When selecting [MCQ], include exactly 4 options but DO NOT include the correct answer or any answer key. "
            "Prefix the output with the chosen type in square brackets (e.g., [MCQ]) then the question text and the options only."
        )
    else:
        types_note = f"Use question type: {preferred_type}. If {preferred_type} is 'MCQ', include exactly 4 options and DO NOT include the correct answer or answer key."

    focus_note = f"If admin has specified focus topics: {focus}. Prefer questions about these topics." if focus else ""

    system_prompt = (
    f"You are a strict AI technical interviewer.\n\n"
    f"The candidate is applying for the role described below.\n\n"
    f"ROLE DESCRIPTION:\n"
    f"{job_description}\n\n"
    f"IMPORTANT VALIDATION RULES:\n"
    f"- If the role description is meaningless, random text, gibberish, or not a real job role,\n"
    f"  respond with exactly: INVALID_JOB_DESCRIPTION\n"
    f"- Do NOT attempt to guess or fix an invalid role\n"
    f"- Do NOT ask any question if the role is invalid\n\n"
    f"QUESTION RULES (ONLY IF ROLE IS VALID):\n"
    f"- Ask exactly ONE interview question\n"
    f"- Question must be strictly related to the role skills\n"
    f"- {level.upper()} difficulty only\n"
    f"- 1 or 2 lines maximum for DESCRIPTIVE/MCQ (coding can be up to 3-5 lines)\n"
    f"- No explanation\n"
    f"- No headings beyond the required type prefix\n"
    f"- Output ONLY the question text (and options if MCQ)\n"
    f"- {types_note}\n"
    f"- {focus_note}\n"
)


    langchain_messages = [SystemMessage(content=system_prompt)]


    langchain_messages = [SystemMessage(content=system_prompt)]

    # Gemini requires at least one HumanMessage
    if not messages:
        langchain_messages.append(
            HumanMessage(content="Start the interview.")
        )
    else:
        for msg in messages:
            langchain_messages.append(
                HumanMessage(content=msg["content"])
            )

    response = llm.invoke(langchain_messages)
    raw = response.content.strip()
    # sanitize any accidental answer keys the model may include (e.g., "(Answer: A)", "Answer: A")
    try:
        # remove parenthesized or bracketed answer hints and any lines containing 'Answer:'
        lines = [l for l in raw.splitlines() if 'Answer:' not in l and '(Answer' not in l and '[Answer' not in l]
        cleaned = '\n'.join(lines).strip()
        # further remove inline patterns like (Answer: A) or [Answer: A]
        cleaned = re.sub(r"\(\s*Answer:.*?\)", '', cleaned)
        cleaned = re.sub(r"\[\s*Answer:.*?\]", '', cleaned)
        cleaned = re.sub(r"Answer:\s*[A-Za-z0-9]+", '', cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            return cleaned
    except Exception:
        pass

    return raw

# ===================== ANSWER EVALUATION =====================

def evaluate_answer(question, answer):
    """Evaluate an answer.

    - If the question is an MCQ, determine the correct option internally (LLM) and
      award 5 for a correct choice and 0 for incorrect.
    - Otherwise, fall back to the generous LLM-based evaluation that returns a
      JSON object with integer score 0-5 and qualified yes/no.
    """

    def _parse_mcq(q_text):
        """Return an ordered dict of options A-D -> text if this looks like an MCQ, else None.

        Supports various formats:
        - Lettered options on separate lines (A) ..., A. ..., A: ...)
        - Inline lettered options (A) foo B) bar C) baz D) qux)
        - Numeric options (1) ... 2) ... etc. mapped to A-D
        - 'Options:' followed by comma/semicolon-separated list
        - Question line followed by exactly 4 option lines
        """
        text = q_text.strip()
        # Remove any leading type prefix like [MCQ]
        if text.upper().startswith('[MCQ]'):
            text = text[5:].strip()

        # 1) Try to capture lettered options anywhere in the text (A) / A. / A: / A- ...)
        letter_matches = re.findall(r'([A-Da-d])\s*[\)\.\:\-]\s*([^\n]+)', text)
        if len(letter_matches) >= 4:
            opts = {m[0].upper(): m[1].strip() for m in letter_matches[:4]}
            return opts

        # 2) Split on lettered markers to handle inline sequences like 'A) foo B) bar'
        parts = re.split(r'(?=[A-Da-d]\s*[\)\.\:\-])', text)
        parsed = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            m = re.match(r'^([A-Da-d])\s*[\)\.\:\-]\s*(.+)$', p, re.DOTALL)
            if m:
                parsed.append((m.group(1).upper(), m.group(2).strip().splitlines()[0].strip()))
        if len(parsed) == 4:
            return dict(parsed)

        # 3) Numeric options like '1) foo' -> map 1->A
        num_matches = re.findall(r'([1-4])\s*[\)\.\:\-]\s*([^\n]+)', text)
        if len(num_matches) >= 4:
            mapping = {'1': 'A', '2': 'B', '3': 'C', '4': 'D'}
            return {mapping[m[0]]: m[1].strip() for m in num_matches[:4]}

        # 4) Options: followed by comma or semicolon separated choices
        m = re.search(r'(?i)options?\s*[:\-]\s*(.+)$', text)
        if m:
            opts_part = m.group(1)
            candidates = [re.sub(r'^[A-Da-d][\)\.\:\-]?\s*', '', c).strip() for c in re.split(r'[;,]', opts_part) if c.strip()]
            if len(candidates) >= 4:
                return dict(zip(['A', 'B', 'C', 'D'], candidates[:4]))

        # 5) As a last resort: if there are multiple non-empty lines, assume Q then 4 option lines
        lines = [l.strip() for l in q_text.splitlines() if l.strip()]
        if len(lines) >= 5:
            cand = lines[1:5]
            if len(cand) == 4:
                return dict(zip(['A', 'B', 'C', 'D'], [re.sub(r'^[A-Da-d][\)\.\:\-]?\s*', '', c).strip() for c in cand]))

        return None

    mcq_opts = _parse_mcq(question)

    if mcq_opts:
        # Ask the LLM privately to give the single correct letter (A-D)
        opt_text = '\n'.join([f"{k}. {v}" for k, v in mcq_opts.items()])
        prompt = (
            "You are an objective MCQ examiner.\n"
            "Given the question and four options, respond ONLY with the single uppercase letter (A, B, C, or D) that is the correct answer.\n"
            "Do NOT provide any explanation or extra text.\n\n"
            f"Question: {question}\n\n"
            f"Options:\n{opt_text}\n"
        )

        try:
            result = llm.invoke([HumanMessage(content=prompt)])
            resp = result.content.strip()
            m = re.search(r'([A-D])', resp, re.I)
            if m:
                correct = m.group(1).upper()
            else:
                # allow numeric responses like '2' -> map to B
                mnum = re.search(r'([1-4])', resp)
                if mnum:
                    mapping = {'1': 'A', '2': 'B', '3': 'C', '4': 'D'}
                    correct = mapping.get(mnum.group(1))
                else:
                    correct = None
        except Exception:
            correct = None

        # Normalize candidate's answer into a letter (A-D) if possible
        ans = (answer or '').strip()
        candidate_letter = None

        # direct letter like 'A' or 'a)'
        m2 = re.search(r'\b([A-Da-d])\b', ans)
        if m2:
            candidate_letter = m2.group(1).upper()

        # numeric answer '1','2' -> map to A/B
        if not candidate_letter:
            mnum = re.search(r'\b([1-4])\b', ans)
            if mnum:
                mapping = {'1': 'A', '2': 'B', '3': 'C', '4': 'D'}
                candidate_letter = mapping.get(mnum.group(1))

        # 'Option B' or 'choice 2'
        if not candidate_letter:
            mopt = re.search(r'(?i)option\s*([A-Da-d1-4])', ans)
            if mopt:
                v = mopt.group(1)
                if v.isdigit():
                    candidate_letter = {'1':'A','2':'B','3':'C','4':'D'}.get(v)
                else:
                    candidate_letter = v.upper()

        # match full or partial text of option (case-insensitive)
        if not candidate_letter:
            norm_ans = ans.lower().strip()
            for letter, text in mcq_opts.items():
                t = text.lower().strip()
                if norm_ans == t or norm_ans in t or t in norm_ans:
                    candidate_letter = letter
                    break
            # last resort fuzzy match
            if not candidate_letter:
                try:
                    from difflib import SequenceMatcher
                    best = (None, 0.0)
                    for letter, text in mcq_opts.items():
                        r = SequenceMatcher(None, norm_ans, text.lower().strip()).ratio()
                        if r > best[1]:
                            best = (letter, r)
                    if best[1] >= 0.7:
                        candidate_letter = best[0]
                except Exception:
                    pass

        if correct and candidate_letter and candidate_letter == correct:
            return {"score": 5, "qualified": "yes"}
        else:
            # If we couldn't map the candidate's answer, treat as incorrect (0)
            return {"score": 0, "qualified": "no"}

    # Non-MCQ fallback: use existing generous LLM-based JSON evaluator
    prompt = (
        "You are a friendly technical interviewer.\n"
        "Evaluate the answer generously.\n\n"
        f"Question: {question}\n"
        f"Answer: {answer}\n\n"
        "Respond ONLY in valid JSON:\n"
        '{"score": 4, "qualified": "yes"}\n'
        "Rules:\n"
        "- score must be INTEGER between 0 and 5\n"
        "- no explanation\n"
    )

    try:
        result = llm.invoke([HumanMessage(content=prompt)])
        content = result.content.strip()
        match = re.search(r'\{.*\}', content)
        if match:
            parsed = json.loads(match.group())
            score = int(parsed.get("score", 0))
            score = max(0, min(5, score))
            return {
                "score": score,
                "qualified": parsed.get("qualified", "no").lower()
            }
    except Exception:
        pass

    return {"score": 0, "qualified": "no"}

# ===================== INTERVIEW FLOW =====================

def start_interview(request):
    if request.method == 'POST':
        form = CandidateForm(request.POST)
        if form.is_valid():
            candidate = Candidate.objects.create(**form.cleaned_data)

            request.session['candidate_id'] = candidate.id
            request.session['messages'] = []
            request.session['question_count'] = 1
            request.session['job_description'] = candidate.job_description

            # Respect admin-configured number of questions (fallback to 4)
            settings_obj = AdminSettings.objects.first()
            max_q = settings_obj.number_of_questions if settings_obj and getattr(settings_obj, 'number_of_questions', None) and settings_obj.number_of_questions > 0 else 4
            request.session['max_questions'] = max_q

            try:
                question = generate_question([], candidate.job_description)
            except Exception as e:
                # LLM unreachable (network/DNS issue). Log and use a safe offline fallback question.
                import logging
                logging.exception("LLM question generation failed, using fallback question")
                question = "[MCQ] (Offline) What is 1+1?\nA) 1\nB) 2\nC) 3\nD) 4"
                messages.error(request, "Question generator temporarily unavailable; using an offline fallback question.")

            request.session['messages'].append({"content": question})

            # include question index, max questions and motion config for template
            settings_obj = AdminSettings.objects.first()
            motion_settings = json.dumps({
                'enabled': bool(getattr(settings_obj, 'enable_motion_detection', False)),
                'pixelThreshold': getattr(settings_obj, 'motion_pixel_threshold', 50),
                'ratioThreshold': getattr(settings_obj, 'motion_ratio_threshold', 0.04),
                'windowSeconds': getattr(settings_obj, 'motion_window_seconds', 60),
                'windowCount': getattr(settings_obj, 'motion_window_count', 3),
                'sampleIntervalMs': getattr(settings_obj, 'motion_sample_interval_ms', 1000),
            })

            # include question index and max questions for template
            return render(request, 'users/question.html', {
                'question': question,
                'form': AnswerForm(),
                'question_count': request.session.get('question_count', 1),
                'max_questions': request.session.get('max_questions', 4),
                'motion_settings': motion_settings,
            })

    return render(request, 'users/start.html', {'form': CandidateForm()})


def answer_question(request):
    candidate = Candidate.objects.get(id=request.session['candidate_id'])
    session_messages = request.session.get('messages', [])
    question_count = request.session.get('question_count', 1)
    job_description = request.session.get('job_description')

    if request.method == 'POST':
        form = AnswerForm(request.POST)
        if form.is_valid():
            answer = form.cleaned_data['answer']
            question = session_messages[-1]['content']

            evaluation = evaluate_answer(question, answer)

            InterviewResponse.objects.create(
                candidate=candidate,
                question=question,
                answer=answer,
                score=evaluation['score']
            )

            # Always read the admin-configured max questions from DB to allow mid-interview updates
            s = AdminSettings.objects.first()
            max_q = s.number_of_questions if s and getattr(s, 'number_of_questions', None) and s.number_of_questions > 0 else 4

            if question_count >= max_q:
                return redirect('interview_results', candidate_id=candidate.id)

            request.session['question_count'] += 1
            session_messages.append({"content": answer})

            try:
                next_question = generate_question(session_messages, job_description)
            except Exception:
                import logging
                logging.exception("LLM question generation failed for next question, using fallback")
                next_question = "[MCQ] (Offline) Which is even?\nA) 1\nB) 3\nC) 4\nD) 7"
                messages.error(request, "Question generator temporarily unavailable; using an offline fallback question for the next prompt.")

            session_messages.append({"content": next_question})
            request.session['messages'] = session_messages

            settings_obj = AdminSettings.objects.first()
            motion_settings = json.dumps({
                'enabled': bool(getattr(settings_obj, 'enable_motion_detection', False)),
                'pixelThreshold': getattr(settings_obj, 'motion_pixel_threshold', 50),
                'ratioThreshold': getattr(settings_obj, 'motion_ratio_threshold', 0.04),
                'windowSeconds': getattr(settings_obj, 'motion_window_seconds', 60),
                'windowCount': getattr(settings_obj, 'motion_window_count', 3),
                'sampleIntervalMs': getattr(settings_obj, 'motion_sample_interval_ms', 1000),
            })

            return render(request, 'users/question.html', {
                'question': next_question,
                'form': AnswerForm(),
                'question_count': request.session.get('question_count', 1),
                'max_questions': request.session.get('max_questions', 4),
                'motion_settings': motion_settings,
            })

    return redirect('start_interview')

# ===================== RESULTS =====================

def interview_results(request, candidate_id):
    candidate = Candidate.objects.get(id=candidate_id)
    responses = InterviewResponse.objects.filter(candidate=candidate)

    scores = [r.score for r in responses if r.score is not None]
    avg_score = sum(scores) / len(scores) if scores else 0

    technical_score = avg_score * 20
    overall_score = min(100, technical_score + 10)

    if avg_score >= 4:
        emotion_score = 85
    elif avg_score >= 3:
        emotion_score = 70
    elif avg_score >= 2:
        emotion_score = 50
    else:
        emotion_score = 30
    
    status = "Qualified" if avg_score >= 3 else "Disqualified"

    # Summary metrics for the compact result card
    interview_date = responses.aggregate(last_date=Max('created_at'))['last_date']
    if interview_date:
        # convert to local timezone (IST) for display
        ist = pytz.timezone('Asia/Kolkata')
        local_date = interview_date.astimezone(ist)
        # Format safely across platforms: remove leading zero in hour
        interview_date_str = local_date.strftime("%B %d, %Y, %I:%M %p").replace(" 0", " ")
    else:
        interview_date_str = 'N/A'

    confidence_level = round((avg_score / 5) * 100, 2)
    accuracy = round(technical_score, 2)

    if avg_score >= 4:
        recommendation = 'Hire'
    elif avg_score >= 3:
        recommendation = 'Consider'
    else:
        recommendation = 'Reject'

    if avg_score >= 4:
        strengths = 'Strong fundamentals'
        weak_areas = 'Minor gaps'
    elif avg_score >= 3:
        strengths = 'Good fundamentals'
        weak_areas = 'Needs improvement'
    elif avg_score >= 2:
        strengths = 'Basic understanding'
        weak_areas = 'Significant gaps'
    else:
        strengths = 'Weak fundamentals'
        weak_areas = 'Needs improvement'

    send_mail(
        "Interview Result",
        f"Average Score: {avg_score:.2f}\nStatus: {status}",
        settings.DEFAULT_FROM_EMAIL,
        [candidate.email],
    )

    return render(request, 'users/results.html', {
        'candidate': candidate,
        'responses': responses,
        'avg_score': avg_score,
        'qualification_status': status,
        'overall_score': overall_score,
        'technical_score': technical_score,
        'emotion_score': emotion_score,
        'interview_date': interview_date_str,
        'confidence_level': confidence_level,
        'accuracy': accuracy,
        'recommendation': recommendation,
        'strengths': strengths,
        'weak_areas': weak_areas,
    })

# ===================== ALL RESULTS =====================

def all_results(request):
    candidates = Candidate.objects.all().order_by('-id')
    results = []

    for c in candidates:
        responses = InterviewResponse.objects.filter(candidate=c)
        scores = [r.score for r in responses if r.score is not None]
        avg_score = sum(scores) / len(scores) if scores else 0
        status = "Qualified" if avg_score >= 3 else "Disqualified"

        interview_date = responses.aggregate(
            last_date=Max('created_at')
        )['last_date']

        results.append({
            'candidate': c,
            'avg_score': avg_score,
            'status': status,
            'date': interview_date
        })

    # Aggregate by candidate name: combine candidates who share the same name
    candidates_list = list(candidates)

    name_groups = {}
    for c in candidates_list:
        name = (c.name or '').strip()
        role = (c.job_description or '').strip()
        resp_qs = InterviewResponse.objects.filter(candidate=c)
        scores = [r.score for r in resp_qs if r.score is not None]
        avg = (sum(scores) / len(scores)) if scores else 0.0
        cnt = resp_qs.count()

        if name not in name_groups:
            name_groups[name] = {
                'candidate_count': 0,
                'total_attempts': 0,
                'high_score': 0.0,
                'role_counts': {}
            }

        name_groups[name]['candidate_count'] += 1
        name_groups[name]['total_attempts'] += cnt
        if avg > name_groups[name]['high_score']:
            name_groups[name]['high_score'] = avg

        if role:
            rc = name_groups[name].setdefault('role_counts', {})
            rc[role] = rc.get(role, 0) + 1

    labels = []
    attempts = []
    high_scores = []
    roles = []

    for name, data in name_groups.items():
        labels.append(f"{name} ({data['candidate_count']})")
        attempts.append(data['total_attempts'])
        high_scores.append(round(data['high_score'], 2))

        # choose most common role for this name group
        role_counts = data.get('role_counts', {})
        if role_counts:
            most_common_role = max(role_counts.items(), key=lambda x: x[1])[0]
        else:
            most_common_role = ''
        roles.append(most_common_role)

    context = {
        'results': results,
        'name_labels_json': json.dumps(labels),
        'attempts_json': json.dumps(attempts),
        'high_scores_json': json.dumps(high_scores),
        'roles_json': json.dumps(roles),
    }

    return render(request, 'users/all_results.html', context)

    # JSON-encode for template JS
    context = {
        'results': results,
        'answer_labels_json': json.dumps(labels),
        'bleu_json': json.dumps(bleu),
        'rouge_json': json.dumps(rouge),
        'bert_json': json.dumps(bert),
        'completeness_json': json.dumps(completeness),
        'total_json': json.dumps(total),
    }

    return render(request, 'users/all_results.html', context)

# ===================== AUTH =====================

def index(request):
    return render(request, 'index.html')


def home(request):
    return render(request, 'home.html')



def register_view(request):
    msg = ''
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')
        image = request.FILES.get('image')

        if not all([name, email, mobile, password, image]):
            msg = "All fields are required."
        else:
            fs = FileSystemStorage()
            filename = fs.save(image.name, image)

            RegisteredUser.objects.create(
                name=name,
                email=email,
                mobile=mobile,
                password=password,
                image=filename,
                is_active=False
            )
            msg = "Registered successfully! Wait for admin approval."

    return render(request, 'register.html', {'msg': msg})


def user_login(request):
    msg = ''
    if request.method == 'POST':
        name = request.POST.get('name')
        password = request.POST.get('password')

        try:
            user = RegisteredUser.objects.get(name=name, password=password)
            if user.is_active:
                ist = pytz.timezone('Asia/Kolkata')
                local_time = timezone.now().astimezone(ist)

                request.session['user_id'] = user.id
                request.session['user_name'] = user.name
                request.session['user_image'] = user.image.url
                request.session['login_time'] = local_time.strftime('%I:%M:%S %p')

                return redirect('user_homepage')
            else:
                msg = "Your account is not activated yet."
        except RegisteredUser.DoesNotExist:
            msg = "Invalid credentials."

    return render(request, 'user_login.html', {'msg': msg})


def admin_login(request):
    msg = ''
    if request.method == 'POST':
        if request.POST.get('name') == 'admin' and request.POST.get('password') == 'admin':
            return redirect('admin_home')
        msg = "Invalid admin credentials."
    return render(request, 'admin_login.html', {'msg': msg})


def admin_home(request):
    return render(request, 'admin_home.html')


def admin_dashboard(request):
    users = RegisteredUser.objects.all()
    settings_obj, _ = AdminSettings.objects.get_or_create(id=1)

    if request.method == "POST":
        # allow updating difficulty and number_of_questions from dashboard if provided
        level = request.POST.get("level")
        if level in ["Easy", "Medium", "Hard"]:
            settings_obj.difficulty_level = level
            settings_obj.save()
        num_q = request.POST.get("number_of_questions")
        if num_q:
            try:
                n = int(num_q)
                if n > 0:
                    settings_obj.number_of_questions = n
                    settings_obj.save()
            except ValueError:
                pass

    return render(request, 'admin_dashboard.html', {
        'users': users,
        'current_level': settings_obj.difficulty_level
    })


def activate_user(request, user_id):
    user = RegisteredUser.objects.get(id=user_id)
    user.is_active = True
    user.save()
    return redirect('admin_dashboard')


def deactivate_user(request, user_id):
    user = RegisteredUser.objects.get(id=user_id)
    user.is_active = False
    user.save()
    return redirect('admin_dashboard')


def delete_user(request, user_id):
    RegisteredUser.objects.get(id=user_id).delete()
    return redirect('admin_dashboard')


def delete_candidate(request, candidate_id):
    """Delete a candidate and cascade-delete their InterviewResponses.

    This view accepts POST only to prevent accidental deletions via GET.
    """
    if request.method == 'POST':
        try:
            Candidate.objects.get(id=candidate_id).delete()
        except Candidate.DoesNotExist:
            pass
    return redirect('all_results')


def delete_candidates(request):
    """Bulk delete candidates by id list from POST['candidate_ids'].

    Accepts POST only. Ignores ids that don't exist.
    """
    if request.method == 'POST':
        ids = request.POST.getlist('candidate_ids')
        if ids:
            # Filter to integer ids for safety
            try:
                ids_int = [int(i) for i in ids]
            except ValueError:
                ids_int = []
            if ids_int:
                Candidate.objects.filter(id__in=ids_int).delete()
    return redirect('all_results')


def tab_violation(request):
    if request.method == "POST":
        count = request.session.get("tab_violation_count", 0) + 1
        request.session["tab_violation_count"] = count

        if count >= 3:
            request.session["auto_disqualified"] = True

        return JsonResponse({"count": count})

    return JsonResponse({"error": "Invalid request"}, status=400)


def vision_analyze(request):
    """Accept a base64 image payload (JSON or form) and save; return a simple analysis.

    Frontend will POST { image: dataURL }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    data_url = request.POST.get('image') or (json.loads(request.body.decode('utf-8')).get('image') if request.body else None)
    if not data_url:
        return JsonResponse({'error': 'No image provided'}, status=400)

    # expected format: data:image/png;base64,AAAA...
    try:
        header, encoded = data_url.split(',', 1)
    except Exception:
        return JsonResponse({'error': 'Invalid image data'}, status=400)

    import base64, os, time
    media_dir = getattr(settings, 'MEDIA_ROOT', 'media')
    out_dir = os.path.join(media_dir, 'vision_snapshots')
    os.makedirs(out_dir, exist_ok=True)

    filename = f"snap_{int(time.time())}.png"
    out_path = os.path.join(out_dir, filename)

    try:
        with open(out_path, 'wb') as f:
            f.write(base64.b64decode(encoded))
    except Exception:
        return JsonResponse({'error': 'Failed to save image'}, status=500)

    # Placeholder processing: if a real GenAI vision integration is available,
    # replace this block with actual API calls to the vision model.
    analysis = {
        'face_detected': True,
        'note': 'Placeholder analysis. Configure GENAI vision integration to replace this.'
    }

    return JsonResponse({'status': 'ok', 'analysis': analysis, 'image_path': os.path.join('vision_snapshots', filename)})


def motion_event(request):
    """Receive motion events from client for logging and optional server-side evaluation.
    Expects JSON: { ratio: float, timestamp: ISO }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except Exception:
        payload = {}

    ratio = None
    try:
        ratio = float(payload.get('ratio', 0))
    except Exception:
        ratio = 0.0

    candidate = None
    candidate_id = request.session.get('candidate_id')
    if candidate_id:
        try:
            candidate = Candidate.objects.get(id=candidate_id)
        except Candidate.DoesNotExist:
            candidate = None

    MotionEvent.objects.create(candidate=candidate, ratio=ratio)

    # Simple server-side check (optional): if many motion events exist for candidate in recent window, respond with action
    action = 'none'
    try:
        settings_obj = AdminSettings.objects.first()
        if candidate and settings_obj and settings_obj.enable_motion_detection:
            window_seconds = getattr(settings_obj, 'motion_window_seconds', 60)
            window_count = getattr(settings_obj, 'motion_window_count', 3)
            recent = MotionEvent.objects.filter(candidate=candidate, created_at__gte=timezone.now() - timezone.timedelta(seconds=window_seconds)).count()
            if recent >= window_count:
                action = 'disqualify'
    except Exception:
        action = 'none'

    return JsonResponse({'status': 'ok', 'action': action})

def user_homepage(request):
    if 'user_id' not in request.session:
        return redirect('user_login')

    return render(request, 'users/user_homepage.html', {
        'user_name': request.session.get('user_name'),
        'user_image': request.session.get('user_image'),
        'login_time': request.session.get('login_time'),
    })


def user_logout(request):
    request.session.flush()
    return redirect('user_login')

# ===================== OTP RESET =====================

otp_storage = {}

def send_otp(email):
    otp = random.randint(100000, 999999)
    otp_storage[email] = otp
    send_mail("Password Reset OTP", f"Your OTP is {otp}", settings.DEFAULT_FROM_EMAIL, [email])
    return otp


def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email")
        if RegisteredUser.objects.filter(email=email).exists():
            send_otp(email)
            request.session["reset_email"] = email
            return redirect("verify_otp")
        messages.error(request, "Email not registered!")
    return render(request, "forgot_password.html")


def verify_otp(request):
    if request.method == "POST":
        if str(otp_storage.get(request.session.get("reset_email"))) == request.POST.get("otp"):
            return redirect("reset_password")
        messages.error(request, "Invalid OTP!")
    return render(request, "verify_otp.html")


def reset_password(request):
    if request.method == "POST":
        email = request.session.get("reset_email")
        user = RegisteredUser.objects.get(email=email)
        user.password = request.POST.get("new_password")
        user.save()
        messages.success(request, "Password reset successful!")
        return redirect("user_login")
    return render(request, "reset_password.html")
def home(request):
    return render(request, 'home.html')


def admin_settings(request):
    settings = AdminSettings.objects.first()
    if not settings:
        settings = AdminSettings.objects.create()
    if request.method == 'POST':
        form = AdminSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            # refresh the settings instance
            settings = AdminSettings.objects.first()
            messages.success(request, 'Settings saved successfully!')
            success_message = 'Settings saved successfully!'
            form = AdminSettingsForm(instance=settings)
            return render(request, 'admin_settings.html', {'form': form, 'current_settings': settings, 'success_message': success_message})
        else:
            # form invalid - fall through to re-render with errors
            return render(request, 'admin_settings.html', {'form': form, 'current_settings': settings})
    else:
        form = AdminSettingsForm(instance=settings)
    return render(request, 'admin_settings.html', {'form': form, 'current_settings': settings})