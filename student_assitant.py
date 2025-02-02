# -*- coding: utf-8 -*-





from transformers import AutoTokenizer, AutoModelForCausalLM
from huggingface_hub import InferenceClient
from sentence_transformers import SentenceTransformer
import torch
import os

class LLM_model:
  def __init__(self, model_type):
    if model_type == 'generator':
      crr = os.path.dirname(os.path.abspath(__file__))+"/models/Gemma"
      self.model_name = crr #"./models/Gemma" # 'mistralai/Mistral-7B-Instruct-v0.3'
      self.model_type = "generator"
    if model_type == 'retriever':
      self.model_name = 'all-MiniLM-L6-v2'
      self.model_type = "retriever"
  def load_model(self):
    if self.model_type == 'generator':
        dtype = torch.bfloat16

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained( self.model_name,torch_dtype=dtype,
              #device_map="cuda",
              )
        #client = InferenceClient( self.model_name, token="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" )
        self.retriever = SentenceTransformer('all-MiniLM-L6-v2')
    else:
      self.model = SentenceTransformer(self.model_name)
  def delete_model(self):
    del self.model
    self.model = None




import faiss
import re
import numpy as np
import pandas as pd

class LLM_func(LLM_model):
  def __init__(self, model_type):
    super().__init__(model_type)
    self.load_model()

  def generate(self, prompt):
    return self.model(prompt)

  def retrieve(self, query, subject_path='data/class7_history'):
      #if self.model_type == 'retriever':
      query_emb = self.retriever.encode(query)
      query_emb = np.array([query_emb]).astype("float32")  # Ensure the query is in the correct shape for FAISS
      df = pd.read_json(f'{subject_path}/class7_history.json')
      chapter_embs = df['key_embedding'].apply(lambda x:np.array(x[0])) ;
      chapter_embs = np.array(chapter_embs.tolist()) ;
      d = chapter_embs.shape[1]  # Dimensionality of the embeddings
      index = faiss.IndexFlatL2(d)  # L2 distance index (Euclidean)
      # Ensure the embeddings are in the correct format
      index.add(chapter_embs)
      distances, indices = index.search(query_emb, 1) ; 
      chapter_num = indices[0][0] +1
      # get relevent paragraph
      df = pd.read_json(f'{subject_path}/chapter{chapter_num}.json')
      para_embs = df['embedding'].apply(lambda x:np.array(x[0])) ; 
      para_embs = np.array(para_embs.tolist())  # Ensure the embeddings are in the correct format
      d = para_embs.shape[1]  # Dimensionality of the embeddings
      index = faiss.IndexFlatL2(d)  # L2 distance index (Euclidean)
      index.add(para_embs)
      distances, indices = index.search(query_emb, 2) ; 
      (index, indx2) = ( indices[0][0] , indices[0][1])
      paragraph = df.iloc[index] ;   p2 = df.iloc[indx2] ; p3 = df.iloc[index-1] 
      return p3['paragraph'] + paragraph['paragraph']+ p2['paragraph']  


  def answer_question(self, question):
    context = self.retrieve(question) ; print('contxt', context)
    #context = "Biden is current president of USA. He succeeded Donald Trump."
    prompt = f"Read the context and answer the question. \n\nContext: {context}\n\nQuestion: {question}\n##Answer:"
    inputs = self.tokenizer.encode(prompt, add_special_tokens=False, return_tensors="pt")
    outputs = self.model.generate(input_ids=inputs.to(self.model.device), max_new_tokens=250)
    generated_answer = self.tokenizer.decode(outputs[0]) + "###End"
    mtch = re.search(r"##Answer:\s(.*?)\s*###End", generated_answer, re.DOTALL)
    #ans = mtch.group(1) if mtch else ""
    answer = mtch.group(1) if mtch else ""
    return answer

  def generate_question(self, difficulty='easy', topic=None):
    if topic == None:
      chapter_num = np.random.randint(1,4)
      df = pd.read_json(f'data/class7_history/chapter{chapter_num}.json')
      context = df.iloc[np.random.randint(0,len(df))]['paragraph'] ; print(context)
    else:
      context = self.retrieve(topic)
    sample_context = "The house is situated on the mountain. The owner has to climb up the mountain daily"
    sample_question = "Why owner has to climb up the mountain daily?"
    sample_context2 = "Barack Obama introduced healthcare system when he was president of USA. "
    sample_question2 = "What did Barack Obama introduce?"
    sample_context3 = "When water is heated above the boiling point, it forms vapurs. These travel up to form clouds"
    sample_question3 = "How are vapours formed?"
    prompt = f"You are tutor to student to conduct test. Generate a easy question based on the following context.The question should \\\
                 match the difficulty level {difficulty} and be inspired by the sample question-answer pair provided. \\\
                 \n\nSample Context: {sample_context}\nSample Question: {sample_question} \n\nSample Context: {sample_context2} \nSample 			Question:{sample_question2} \\\
                  \n\nSample Context:{sample_context3} \nSample Question:{sample_question3}\n\nContext:{context}\n##Question: "
    inputs = self.tokenizer.encode(prompt, add_special_tokens=False, return_tensors="pt")
    outputs = self.model.generate(input_ids=inputs.to(self.model.device), max_new_tokens=250)
    generated_answer = self.tokenizer.decode(outputs[0]) + "###End"
    mtch = re.search(r"##Question:\s(.*?)\s*###End", generated_answer, re.DOTALL)
    question = mtch.group(1) if mtch else ""
    return question 






import os, re , json
import pandas as pd
import spacy
import pdfplumber
from transformers import pipeline

class LLM_enc(LLM_model):
  def __init__(self, subject):
    super().__init__(model_type='retriever')
    self.subject = subject
    self.summarizer = pipeline("summarization",framework='pt')
    self.load_model()
    #self.data = self.prepare_data_json()

  def get_chapter_number_name(self, filename):
    chapter_num = re.search(r'Chapter-(\d+)', filename)
    chapter_num = chapter_num.group(1) if chapter_num else "Unknown"
    # Split the filename to get the title (after the chapter number)
    title = re.split(r'Chapter-\d+-', filename)
    chapter_title = title[1].replace('.pdf', '').replace('-', ' ') if len(title) > 1 else "Unknown Title"
    return chapter_num, chapter_title

  def read_pdf(self, file_path):
    with pdfplumber.open(file_path) as pdf:
      text = ''
      for page in pdf.pages:
        text += page.extract_text()
      return text
  def extract_keywords(self, text):
    nlp = spacy.load("en_core_web_sm")
    doc = nlp(text)
    keywords = list(set([chunk.text for chunk in doc.noun_chunks]))
    return keywords  
	
  def get_chapter_emb(self ):
    pass
  def get_paraghraph_emb(self, chapter_text, chapter_number, folder_path):
    data = []
    chapter_text = self.split_long_paragraph(chapter_text, 512)
    for num, chunk in enumerate(chapter_text):
        para_embedding = self.model.encode(chunk, convert_to_tensor=True).cpu().numpy().reshape(1, -1)
        data.append([num, para_embedding, chunk])
        df = pd.DataFrame(data, columns=["number","embedding","paragraph"])
    json_data = df.to_json(orient='records')
    json_file = os.path.join(folder_path, f'chapter{chapter_number}.json')
    with open(json_file, 'w') as json_file:
      json_file.write(json_data)

  def split_long_paragraph(self, paragraph, max_length=512):
        """Split a single paragraph into smaller chunks if it exceeds max_length."""
        if len(paragraph) <= max_length:
            return [paragraph]
        else:
            # Split the long paragraph into sentences using regex or period-based approach
            sentences = re.split(r'(?<=[.!?]) +', paragraph)
            chunks = []
            current_chunk = ""

            # Step 2: Group sentences into chunks of max_length
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 <= max_length:
                    current_chunk += " " + sentence if current_chunk else sentence
                else:
                    chunks.append(current_chunk)
                    current_chunk = sentence

            # Append the remaining chunk if any
            if current_chunk:
                chunks.append(current_chunk)

            return chunks
  def summarize_text(self, chapter_text, max_length=250, min_length=30):
    summarized_paragraph = ""
    chapter_text = self.split_long_paragraph(chapter_text, 512)
    for chunk in chapter_text:
        #summary = self.summarizer(chunk, max_length=250, min_length=30, do_sample=False)
        summarized_paragraph += chunk #summary[0]['summary_text']
    while len(summarized_paragraph) > 512:
      chunks = self.split_long_paragraph(summarized_paragraph, 512)
      summarized_paragraph = ""
      for chunk in chunks:
        summary = self.summarizer(chunk, max_length=250, min_length=30, do_sample=False)
        summarized_paragraph += summary[0]['summary_text']
    return summarized_paragraph

  def process_textbook_folder(self, folder_path):
    """Process PDFs in a folder, extract summaries and keywords per chapter, and store in DataFrame."""
    data = []

    for filename in os.listdir(folder_path):
        if filename.endswith(".pdf"):
            chapter_num, chapter_title = self.get_chapter_number_name(filename)
            pdf_path = os.path.join(folder_path, filename)
            chapter_text = self.read_pdf(pdf_path)

            self.get_paraghraph_emb(chapter_text,chapter_num, folder_path)

            summary = self.summarize_text(chapter_text)
            keywords = extract_keywords(chapter_text)
            chapter_embedding = self.model.encode(summary, convert_to_tensor=True).cpu().numpy().reshape(1, -1)
            data.append([chapter_num,chapter_embedding, summary, keywords])

            self.get_paraghraph_emb(chapter_text,chapter_num, folder_path)
    df = pd.DataFrame(data, columns=["Chapter", "embedding", "Summary", "Keywords"])
    json_data = df.to_json(orient='records')
    json_file = os.path.join(folder_path, f'{self.subject}.json')
    with open(json_file, 'w') as json_file:
      json_file.write(json_data)
    return df

#enc = LLM_enc('class7_history')
#enc.process_textbook_folder('/content/drive/MyDrive/StartUp/data/class7_history')



import streamlit as st

def main():
    st.title("AI-Powered Learning App")

    # Option to select between "Chat" and "Practice Test"
    option = st.sidebar.selectbox("Choose an option", ["Chat", "Practice Test"])
    llm = LLM_func('generator')

    if option == "Chat":
        st.header("Chat with AI")

        # Chat interface
        if 'chat_history' not in st.session_state:
            st.session_state['chat_history'] = []  # Store chat history

        user_query = st.text_input("Ask your question:")
        if st.button("Send"):
            if user_query:
                # Get response from the chatbot
                response = llm.answer_question(user_query)
                #response = get_chat_response(user_query)

                # Add query and response to chat history
                st.session_state['chat_history'].append((user_query, response))

        # Display the chat history
        st.subheader("Chat History")
        for query, response in st.session_state['chat_history']:
            st.write(f"**You:** {query}")
            st.write(f"**AI:** {response}")
            st.write("---")

    elif option == "Practice Test":
        st.header("Practice Test")

        # Test session state management
        if 'question_index' not in st.session_state:
            st.session_state['question_index'] = 0
            st.session_state['user_answers'] = []

        # Display the current question
        if st.session_state['question_index'] < 10:
	    #question = llm.generate_question()
            st.write(f"Question {llm.generate_question()}")
            user_answer = st.text_input("Your Answer:")

            if st.button("Submit Answer"):
                if user_answer:
                    # Store the user's answer
                    st.session_state['user_answers'].append(user_answer)
                    # Move to the next question
                    st.session_state['question_index'] += 1

        # After 10 questions, generate the report
        if st.session_state['question_index'] == 10:
            st.subheader("Test Completed!")
            report = "" #evaluate_answers(st.session_state['user_answers'])
            st.write("\n".join(report))

            if st.button("Reset Test"):
                # Reset the test session
                st.session_state['question_index'] = 0
                st.session_state['user_answers'] = []

# Run the Streamlit app

main()





