from flask import Flask, request, jsonify, Response, send_file
import PyPDF2
import re
import openai
import json
import time
import threading

app = Flask(__name__)

@app.route('/pdf',methods=['POST'])
def function():
    files = request.files.getlist('file')
    openai.api_key = request.form['openai_key']
    if len(files) == 0:
        return 'No file uploaded', 400


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
    
    converted_text = convert_pdf_to_text(files)
    processed_text = preprocess_text(converted_text)
    
    sentences = get_sentences(processed_text)
    combined_paras = combined_paragraphs(sentences)
    jsonl_file = generate_jsonl(combined_paras)
    #response = Response(processed_text, mimetype='text/plain')
    return send_file(jsonl_file, as_attachment=True,download_name=jsonl_file)

if __name__ == '__main__':
    app.run()