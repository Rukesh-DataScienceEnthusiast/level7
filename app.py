import os
from flask import Flask, render_template, request
import random
import re
from pdfminer.high_level import extract_text
import docx2txt
import pymysql
import google.generativeai as genai


app = Flask(__name__)

# Set the Google API key
os.environ['GOOGLE_API_KEY'] = "AIzaSyAFQB8eJVkp4N8fA-HrvPeWz1PFvsOopVU"

# Configure the generative AI module with the API key
genai.configure(api_key=os.environ['GOOGLE_API_KEY'])

# Initialize the GenerativeModel with the desired model (e.g., "gemini-pro")
model = genai.GenerativeModel('gemini-pro')

# Global list to store questions and answers
questions_list = []

def extract_text_from_pdf(pdf_path):
    return extract_text(pdf_path)

def extract_text_from_docx(docx_path):
    return docx2txt.process(docx_path)

def extract_skills_from_resume(text, skills_list):
    skills = []
    for skill in skills_list:
        pattern = r"\b{}\b".format(re.escape(skill))
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            skills.append(skill)
    return skills

def remove_keywords(text, keywords):
    for keyword in keywords:
        text = text.replace(keyword, '')
    return text.strip()  # Remove leading and trailing spaces


def remove_unwanted_elements(options):
    # Create a list of all 26 alphabets in lowercase and uppercase
    alphabets = [chr(i) for i in range(ord('a'), ord('z')+1)] + [chr(i) for i in range(ord('A'), ord('Z')+1)]

    # Create the keywords in the specified formats
    keywords = ["**Options:**", "**Explanation:**", " **Correct Answer:**", " **Option 1:**", " **Option 2:**", " **option4:** ", " **Option 5:**", "*", "**", "**Correct Answer:** ", " Option 1:", " Option 2:", " Option 4:", " Option 5:", "Answer Options:", "```","Question: ", "Questions: ","Question","Questions","Multiple Choice Options:","Multiple Choice Options", "A.A", "B.B", "C.C", "D.D", "A.A.", "B.B.", "C.C.", "D.D.", "Answer: ","Answers: "]+ \
                [f"**Option {alpha}:**" for alpha in alphabets] + \
                [f"**Question:**", "(a)", "(A)", "(b)", "(B)", "(c)", "(C)", "(d)", "(D)", "(e)", "(E)" ""] + \
                [f"**{alpha}.**" for alpha in alphabets] + \
                [f"**{alpha}.**," for alpha in alphabets] + \
                [f"**({alpha})**" for alpha in alphabets] + \
                [f"**,{alpha}" for alpha in alphabets] + \
                ["Option 1:", "Option 2:", "Option 3:", "Option 4:", "Option 1", "Option 2", "Option 3", "Option 4",
                 "Option A:", "Option B:", "Option C:", "Option D:", "Option A", "Option B", "Option C", "Option D",
                 "Option a:", "option b:", "option c:", "option d:", "option a", "option b", "option c", "option d",
                 "(a)", "(b)", "(c)", "(d)", "a)", "b)", "c)", "d)", "(A)", "(B)", "(C)", "(D)", "A).", "B)", "C)", "D)",
                 "Choice 1:", "Choice 2:", "Choice 3:", "Choice 4:", "Choice 1", "Choice 2", "Choice 3", "Choice 4",
                 "Choice A:", "Choice B:", "Choice C:", "Choice D:", "Choice A", "Choice B", "Choice C", "Choice D",
                 "Choice a:", "Choice b:", "Choice c:", "Choice d:", "Choice a", "Choice b", "Choice c", "Choice d",
                 "A. A.", "B. B.", "C. C.", "D. D."]

    cleaned_options = []
    for option in options:
        cleaned_option = remove_keywords(option, keywords)
        if cleaned_option:  # Check if the cleaned option is not an empty string
            cleaned_options.append(cleaned_option)
    return cleaned_options


def generate_questions_for_skills(selected_skills, num_questions, question_mode):
    global questions_list
    questions_list = []  # Clear previous questions

    def generate_question_and_options(skill):
        try:
            question_response = model.generate_content(f"Ask a question related to {skill}")
            if not question_response or not question_response.text:
                raise ValueError("Invalid response for question generation")

            options_response = model.generate_content(f"Generate options for the question: {question_response.text}")
            if not options_response or not options_response.text:
                raise ValueError("Invalid response for options generation")

            processed_options = [opt.strip() for opt in options_response.text.split('\n') if opt.strip()]
            if not processed_options:
                raise ValueError("No options generated")

            correct_answer = processed_options[0]  # Assume the first option is correct for simplicity

            # Shuffle options to avoid bias
            random.shuffle(processed_options)

            # Ensure correct answer is among the options
            if correct_answer not in processed_options:
                processed_options[0] = correct_answer

            # Format options with A, B, C, D
            labeled_options = {f"{chr(65 + i)}": option for i, option in enumerate(processed_options[:4])}

            return {
                'id': len(questions_list) + 1,
                'question': question_response.text,
                'options': labeled_options,
                'correct': correct_answer,
                'user_answer': ''
            }
        except Exception as e:
            print(f"Error generating question for skill {skill}: {e}")
            return None

    if question_mode == 'separate':
        for skill in selected_skills:
            for _ in range(num_questions):
                question_data = generate_question_and_options(skill)
                if question_data:
                    questions_list.append(question_data)
    elif question_mode == 'combined':
        total_questions = num_questions  # Total questions when combined
        for _ in range(total_questions):
            skill = random.choice(selected_skills)
            question_data = generate_question_and_options(skill)
            if question_data:
                questions_list.append(question_data)

    return questions_list

@app.route('/')
def index():
    return render_template('res.html')

@app.route('/upload', methods=['POST'])
def upload_resume():
    if 'resume' not in request.files:
        return 'No file uploaded'

    resume_file = request.files['resume']
    if resume_file.filename == '':
        return 'No file selected'

    upload_dir = 'upload'
    os.makedirs(upload_dir, exist_ok=True)
    resume_path = os.path.join(upload_dir, resume_file.filename)
    resume_file.save(resume_path)

    if resume_path.endswith('.pdf'):
        text = extract_text_from_pdf(resume_path)
    elif resume_path.endswith('.docx'):
        text = extract_text_from_docx(resume_path)
    else:
        return 'Unsupported file format'

    skills_list = ['Python', 'Java', 'C', 'C++', 'SQL', 'MongoDB', 'Excel', 'Machine learning', 'R']
    extracted_skills = extract_skills_from_resume(text, skills_list)

    return render_template('options.html', skills=extracted_skills)

@app.route('/generate_questions', methods=['POST'])
def generate_questions():
    selected_skills = request.form.getlist('selected_skills[]')
    num_questions = int(request.form.get('num_questions'))
    question_mode = request.form.get('question_mode')
    generated_questions = generate_questions_for_skills(selected_skills, num_questions, question_mode)

    return render_template('questions.html', questions=generated_questions)

@app.route('/submit_answers', methods=['POST'])
def submit_answers():
    global questions_list
    for question in questions_list:
        user_answer_key = f"user_answer_{question['id']}"
        if user_answer_key in request.form:
            question['user_answer'] = request.form[user_answer_key]

    return render_template('answers.html', questions=questions_list)

if __name__ == '__main__':
    app.run(debug=True)
