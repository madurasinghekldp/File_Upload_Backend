from flask import Flask, request, jsonify, Response, send_file
from flask_socketio import SocketIO, emit
import jwt
import PyPDF2
import re
import openai
import json
import time
import threading
import subprocess
import jsonlines
import os
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
socketio = SocketIO(app)

def convert_pdf_to_text(files):
        print("convert_pdf_to_text\n")
        text = ''
        for file in files:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text()
        return text
    
def preprocess_text(text):
        print("preprocess_text\n")
        # Remove unwanted characters, symbols, or formatting
        text = re.sub(r'\n', ' ', text)  # Remove newlines
        text = re.sub(r'\s+', ' ', text)  # Remove extra whitespaces
        text = re.sub(r'\.{2,}', '.', text)
        # Additional preprocessing steps can be added here

        return text

def get_sentences(text):
        print("get_sentences\n")
        # Split text into sentences using regular expressions
        sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', text)

        return sentences

def combined_paragraphs(sentences):
        print("combined_paragraphs\n")
        paragraphs = []
        for i in range(0, len(sentences), 2):
            paragraph = ' '.join(sentences[i:i+2])
            paragraphs.append(paragraph)
        return paragraphs
    
def openai_question(input_prompt):
        #print("openai_question\n")
        template = """We particularly welcome the discussion around the possible inclusion of smart line voltage thermostats. Although currently less prevalent on the market, on the North American scale, electric heat is bound to increase in the future given the move to electrification and the energy transition.
                    make 4 questions and give answers bases on content of above paragraph. | Question: What is the focus of the discussion? Answer: The focus of the discussion is on the possible inclusion of smart line voltage thermostats. | Question: Why are smart line voltage thermostats currently less prevalent on the market? Answer: Smart line voltage thermostats are currently less prevalent on the market. | Question: What factor is expected to drive the increase in electric heat in the future? Answer: The move to electrification and the energy transition are expected to drive the increase in electric heat in the future. | Question: On which scale is electric heat bound to increase? Answer: Electric heat is bound to increase on the North American scale.
                    
                    {input_prompt}
                    make new 4 questions and give answers bases on content of second paragraph. |     |     |    |   
                    """

        prompt = template.format(input_prompt=input_prompt)

        try:
            completion = openai.Completion.create(
                engine="davinci",
                prompt=prompt,
                max_tokens=1000,
                temperature=0.7
            )

            message = completion.choices[0].text
            output_list = message.split("|")
            #questions = [sentence for sentence in output_list[1:] if sentence.startswith("Question:")]

            out_index = []
            
            if output_list:
                return output_list[1:]
        except Exception as e:
            print(f"An error occurred: {e}")
            
            return None
        
def generate_jsonl(paragraphs):
        print("generate_jsonl\n")
        pattern = r"Question: (.*?) Answer: (.*?)$"
        
        with open('output.jsonl', 'w') as file:
        
            # Print the sentences
            for paragraph in paragraphs:
                #print("paragraph "+ paragraph)
                
                try:
                    question = openai_question(paragraph)
                    for item in question:
                        #print(item.strip())
                        match = re.search(pattern, item.strip())
                        
                        Question = match.group(1)
                        Answer = match.group(2)
                        
                        json_obj = {
                        'prompt': Question,
                        'completion': Answer
                        }
                        json_line = json.dumps(json_obj)
                        file.write(json_line + '\n')
                        
                except:
                    continue
                
        return 'output.jsonl'  

def fine_tune_model(output_file, api_key, model_name,email):
    
    local_file = output_file
    train_file_id_or_path = "output_prepared.jsonl"
    base_model = model_name

    # Prepare data
    try:
        prepare_data_command = f"openai -k {api_key} tools fine_tunes.prepare_data -f {local_file}"
        process = subprocess.Popen(prepare_data_command, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)

        output, _ = process.communicate(input=b"y\ny\ny\ny\ny\ny\ny\ny\ny\ny\n")  # Wait for the command to complete and capture the output
        send_email(email, 'Preprocessing data has been started.', 'Preprocessing data has been started for fine-tuning and we will provide progrerss afterwards.')
        try:
            os.remove(local_file)
        except OSError as e:
            print(f"Error deleting the file: {e}")
            return None
    except Exception as e:
        print('Error at preparing data: ',e)
        send_email(email, 'Preprocessing data is failed', 'Error at preparing data: '+e)
        try:
            os.remove("output_prepared.jsonl")
        except OSError as e:
            print(f"Error deleting the file: {e}")
            return None
        return None
        
    """ try:
        output = output.decode("utf-8")  # Convert the output bytes to a string
    except UnicodeDecodeError:
        output = output.decode("latin-1")   # Convert the output bytes to a string
    print('output is: ',output)  """



    # Create fine-tuned model
    try:
        create_model_command = f"openai -k {api_key} api fine_tunes.create -t {train_file_id_or_path} -m {base_model}"
        process = subprocess.Popen(create_model_command, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)

        output,_ = process.communicate(input=b"\n")
        send_email(email, 'Fine-tune job started', 'Fine-tune job started started for fine-tuning and we will provide progrerss afterwards.')
    except Exception as e:
        print('Error at create fine-tuned model: ',e)
        send_email(email, 'Fine-tune job failed', 'Error at create fine-tuned model: '+e)
        try:
            os.remove("output_prepared.jsonl")
        except OSError as e:
            print(f"Error deleting the file: {e}")
            return None
        return None

    try:
        output = output.decode("utf-8") # Convert the output bytes to a string
    except UnicodeDecodeError:
        output = output.decode("latin-1")

        
            
    pattern = r"openai api fine_tunes.follow -i (\S+)"
    match = re.search(pattern, output)
    if match:
        fine_tune_job_id = match.group(1)
        print(f"fine_tune_job_id: {fine_tune_job_id}")
    else:
        print("Fine-tune job ID not found.")
        try:
            os.remove("output_prepared.jsonl")
        except OSError as e:
            print(f"Error deleting the file: {e}")
            return None


    # Follow fine-tuning progress
    try:
        if fine_tune_job_id:
            follow_progress_command = f"openai -k {api_key} api fine_tunes.follow -i {fine_tune_job_id}"
            subprocess.run(follow_progress_command, shell=True)
            print("The model will be created few hours later.")
            send_email(email, 'Fine-tuning model started', 'Fine-tuning the model started.The model will be created few hours later.')
            file_path = "output_prepared.jsonl"  # Replace with the actual file path
            try:
                os.remove(file_path)
            except OSError as e:
                print(f"Error deleting the file: {e}")
                return None
    except Exception as e:
        print('Error at fine-tuning progress: ',e)
        try:
            os.remove("output_prepared.jsonl")
        except OSError as e:
            print(f"Error deleting the file: {e}")
            return None
        return None
    return True
    
def is_jsonl_file_empty(file_path):
    with jsonlines.open(file_path) as reader:
        for line in reader.iter():
            if line:
                return False
    return True 

async def process_jsonl_file_async(combined_paras,email):
    jsonl_file = generate_jsonl(combined_paras)
    is_empty = is_jsonl_file_empty(jsonl_file)

    if not is_empty:
        output_file = jsonl_file  # Path to the output.jsonl file
        api_key = openai.api_key  # Your OpenAI API key
        model_name = 'curie'  # The base model to use for fine-tuning

        try:
            # Call the function to start the fine-tuning process asynchronously
            resultFT = await asyncio.to_thread(fine_tune_model, output_file, api_key, model_name,email)

            with app.app_context():
                if resultFT is not None:
                    socketio.emit('task_update', 'Fine-Tune Success')
                    send_email(email, 'The Fine-tune task completed', 'Your fine-tune task successfully completed and please check the status from your account.')
                else:
                    socketio.emit('task_update', 'Fine-Tune Failure')
                    send_email(email, 'The Fine-tune task failed', 'Unfortunately your fine-tune task failed for some reason.')
        except Exception as e:
            with app.app_context():
                socketio.emit('task_update', f'Fine-Tune Failure: {str(e)}')
                send_email(email, 'The Fine-tune task failed', 'Unfortunately your fine-tune task failed for some reason.')
    else:
        # Emit the message to the client asynchronously using socketio
        with app.app_context():
            socketio.emit('task_update', 'Fine-Tune Failure: Empty data')
            send_email(email, 'The Fine-tune task failed', 'Unfortunately your fine-tune task failed for some reason.')
            


def run_async_task(combined_paras,email):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(process_jsonl_file_async(combined_paras,email))

def send_email(recipient, subject, body):
    # Replace the following placeholders with your email credentials and settings
    sender_email = 'clagri2023@gmail.com'
    sender_password = 'cqnbrmcxqznmzxxa'
    smtp_server = 'smtp.gmail.com'
    smtp_port = 587  # Or the appropriate port for your email service

    # Create a MIMEText object to represent the email
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient
    msg['Subject'] = subject

    # Attach the body of the email
    msg.attach(MIMEText(body, 'plain'))

    # Connect to the SMTP server and send the email
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()  # Use TLS encryption
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient, msg.as_string())     
    
    
@app.route('/pdf',methods=['POST'])
def function():
    token = request.headers.get('Authorization')
    email = request.form.get('email')
    if token:
        try:
            # Verify and decode the token
            decoded_token = jwt.decode(token, 'dulan/sahan', algorithms=['HS256'])
            # Perform additional checks or operations based on the decoded token
            # ...
            #return 'Authorized'
        except jwt.ExpiredSignatureError:
            return 'Token expired', 401
        except jwt.InvalidTokenError:
            return 'Invalid token', 401
    

    #files = request.files.getlist('file')
    files = []
    for key, value in request.files.items():
        if 'file' in key:
            files.append(value)
    openai.api_key = request.form['openai_key']
    if len(files) == 0:
        return 'No file uploaded', 400

   
    converted_text = convert_pdf_to_text(files)
    processed_text = preprocess_text(converted_text)
    
    sentences = get_sentences(processed_text)
    combined_paras = combined_paragraphs(sentences)
    
    thread = threading.Thread(target=run_async_task, args=(combined_paras,email,))
    thread.start()
    send_email(email, 'The Fine-tune task has been started', 'Your fine-tune task has been started and we will provide progrerss afterwards.')
    return 'Task started', 200
    
    

if __name__ == '__main__':
    socketio.run(app)