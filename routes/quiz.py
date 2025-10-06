# routes/quiz.py
import json, time, uuid, asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import Form, HTTPException

from helpers.setup import app, rag, logger, nvidia_rotator, gemini_rotator
from helpers.models import MessageResponse, QuizResponse, QuizResultResponse
from utils.api.router import select_model, generate_answer_with_model, NVIDIA_SMALL, NVIDIA_MEDIUM, NVIDIA_LARGE
from utils.analytics import get_analytics_tracker


@app.post("/quiz/create", response_model=MessageResponse)
async def create_quiz(
    user_id: str = Form(...),
    project_id: str = Form(...),
    questions_input: str = Form(...),
    time_limit: str = Form(...),
    documents: str = Form(...)
):
    """Create a quiz from selected documents"""
    try:
        # Parse documents
        selected_docs = json.loads(documents)
        time_limit_minutes = int(time_limit)
        
        logger.info(f"[QUIZ] Creating quiz for user {user_id}, project {project_id}")
        logger.info(f"[QUIZ] Documents: {selected_docs}")
        logger.info(f"[QUIZ] Questions input: {questions_input}")
        logger.info(f"[QUIZ] Time limit: {time_limit_minutes} minutes")
        
        # Step 1: Parse user input to determine question counts
        question_config = await parse_question_input(questions_input, nvidia_rotator)
        logger.info(f"[QUIZ] Parsed question config: {question_config}")
        
        # Step 2: Get document summaries and key topics
        document_summaries = await get_document_summaries(user_id, project_id, selected_docs)
        key_topics = await extract_key_topics(document_summaries, nvidia_rotator)
        logger.info(f"[QUIZ] Extracted {len(key_topics)} key topics")
        
        # Step 3: Create question generation plan
        generation_plan = await create_question_plan(
            question_config, key_topics, nvidia_rotator
        )
        logger.info(f"[QUIZ] Created generation plan with {len(generation_plan)} tasks")
        
        # Step 4: Generate questions and answers
        questions = await generate_questions_and_answers(
            generation_plan, document_summaries, nvidia_rotator
        )
        logger.info(f"[QUIZ] Generated {len(questions)} questions")
        
        # Step 5: Create quiz record
        quiz_id = str(uuid.uuid4())
        quiz_data = {
            "quiz_id": quiz_id,
            "user_id": user_id,
            "project_id": project_id,
            "questions": questions,
            "time_limit": time_limit_minutes,
            "documents": selected_docs,
            "created_at": datetime.now(timezone.utc),
            "status": "ready"
        }
        
        # Store quiz in database
        rag.db["quizzes"].insert_one(quiz_data)
        
        return MessageResponse(message="Quiz created successfully", quiz=quiz_data)
        
    except Exception as e:
        logger.error(f"[QUIZ] Quiz creation failed: {e}")
        raise HTTPException(500, detail=f"Failed to create quiz: {str(e)}")


@app.post("/quiz/submit", response_model=MessageResponse)
async def submit_quiz(
    user_id: str = Form(...),
    project_id: str = Form(...),
    quiz_id: str = Form(...),
    answers: str = Form(...)
):
    """Submit quiz answers and get results"""
    try:
        # Parse answers
        user_answers = json.loads(answers)
        
        # Get quiz data
        quiz = rag.db["quizzes"].find_one({
            "quiz_id": quiz_id,
            "user_id": user_id,
            "project_id": project_id
        })
        
        if not quiz:
            raise HTTPException(404, detail="Quiz not found")
        
        # Mark answers
        results = await mark_quiz_answers(quiz["questions"], user_answers, nvidia_rotator)
        
        # Store results
        result_data = {
            "quiz_id": quiz_id,
            "user_id": user_id,
            "project_id": project_id,
            "answers": user_answers,
            "results": results,
            "submitted_at": datetime.now(timezone.utc)
        }
        
        rag.db["quiz_results"].insert_one(result_data)
        
        return MessageResponse(message="Quiz submitted successfully", results=results)
        
    except Exception as e:
        logger.error(f"[QUIZ] Quiz submission failed: {e}")
        raise HTTPException(500, detail=f"Failed to submit quiz: {str(e)}")


async def parse_question_input(questions_input: str, nvidia_rotator) -> Dict[str, int]:
    """Parse user input to determine MCQ and self-reflect question counts using Llama model"""
    system_prompt = """You are an expert at parsing user requests for quiz questions. 
    Given a user's input about how many questions they want, extract the number of MCQ and self-reflect questions.
    
    Return ONLY a JSON object with this exact format:
    {
        "mcq": <number of multiple choice questions>,
        "sr": <number of self-reflect questions>
    }
    
    Rules:
    - If user specifies "MCQ" or "multiple choice", count those as mcq
    - If user specifies "self-reflect", "self-reflection", "reflection", or "open-ended", count those as sr
    - If user says "total" or just gives a number, split 70% MCQ and 30% self-reflect
    - If user doesn't specify types, assume they want MCQ questions
    - Always return valid numbers (0 or positive integers)
    """
    
    user_prompt = f"User input: {questions_input}\n\nExtract the question counts:"
    
    try:
        # Use NVIDIA_SMALL for parsing
        response = await generate_answer_with_model(
            selection={"provider": "nvidia", "model": NVIDIA_SMALL},
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator,
            user_id="system",
            context="quiz_parsing"
        )
        
        # Parse JSON response
        config = json.loads(response.strip())
        return {
            "mcq": int(config.get("mcq", 0)),
            "sr": int(config.get("sr", 0))
        }
        
    except Exception as e:
        logger.warning(f"[QUIZ] Failed to parse question input: {e}")
        # Fallback: assume 10 MCQ questions
        return {"mcq": 10, "sr": 0}


async def get_document_summaries(user_id: str, project_id: str, documents: List[str]) -> str:
    """Get comprehensive summaries from selected documents using NVIDIA models"""
    summaries = []
    
    for doc in documents:
        try:
            # Get file summary
            file_data = rag.get_file_summary(user_id=user_id, project_id=project_id, filename=doc)
            if file_data and file_data.get("summary"):
                summaries.append(f"[{doc}] {file_data['summary']}")
            
            # Get additional chunks for more context
            chunks = rag.get_file_chunks(user_id=user_id, project_id=project_id, filename=doc, limit=30)
            if chunks:
                chunk_text = "\n".join([chunk.get("content", "") for chunk in chunks[:15]])
                summaries.append(f"[{doc} - Additional Content] {chunk_text[:3000]}...")
                
        except Exception as e:
            logger.warning(f"[QUIZ] Failed to get summary for {doc}: {e}")
            continue
    
    # Use NVIDIA_LARGE for comprehensive analysis if content is long
    combined_summaries = "\n\n".join(summaries)
    if len(combined_summaries) > 5000:
        logger.info(f"[QUIZ] Using NVIDIA_LARGE for long context analysis ({len(combined_summaries)} chars)")
        return await enhance_document_analysis(combined_summaries, nvidia_rotator)
    
    return combined_summaries


async def enhance_document_analysis(document_content: str, nvidia_rotator) -> str:
    """Use NVIDIA_LARGE to enhance document analysis for long contexts"""
    system_prompt = """You are an expert at analyzing educational documents and extracting key information for quiz generation.
    Given document content, create a comprehensive summary that focuses on:
    - Main concepts and theories
    - Important facts and details
    - Key processes and procedures
    - Critical thinking points
    - Relationships between concepts
    
    Provide a structured summary that will be useful for generating high-quality quiz questions.
    """
    
    user_prompt = f"Document content:\n{document_content[:8000]}...\n\nCreate a comprehensive analysis:"
    
    try:
        response = await generate_answer_with_model(
            selection={"provider": "nvidia_large", "model": NVIDIA_LARGE},
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator,
            user_id="system",
            context="quiz_document_analysis"
        )
        return response
    except Exception as e:
        logger.warning(f"[QUIZ] Failed to enhance document analysis: {e}")
        return document_content


async def extract_key_topics(document_summaries: str, nvidia_rotator) -> List[str]:
    """Extract key topics from document summaries using NVIDIA_SMALL for efficiency"""
    system_prompt = """You are an expert at analyzing educational content and extracting key topics.
    Given document summaries, identify the main topics and concepts that would be suitable for quiz questions.
    
    Return a JSON array of topic strings, focusing on:
    - Main concepts and theories
    - Important facts and details
    - Key processes and procedures
    - Critical thinking points
    
    Limit to 10-15 most important topics. Be specific and concise.
    """
    
    user_prompt = f"Document summaries:\n{document_summaries[:4000]}...\n\nExtract key topics:"
    
    try:
        # Use NVIDIA_SMALL for topic extraction (efficient for this task)
        response = await generate_answer_with_model(
            selection={"provider": "nvidia", "model": NVIDIA_SMALL},
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator,
            user_id="system",
            context="quiz_topic_extraction"
        )
        
        topics = json.loads(response.strip())
        return topics if isinstance(topics, list) else []
        
    except Exception as e:
        logger.warning(f"[QUIZ] Failed to extract topics: {e}")
        return ["General Knowledge", "Key Concepts", "Important Details"]


async def create_question_plan(question_config: Dict, key_topics: List[str], nvidia_rotator) -> List[Dict]:
    """Create a plan for question generation using NVIDIA_MEDIUM (Qwen) for reasoning"""
    system_prompt = """You are an expert at creating quiz question generation plans.
    Given question counts and topics, create a detailed plan for generating questions.
    
    Return a JSON array of task objects, each with:
    - description: what type of questions to generate
    - complexity: "high", "medium", or "low" (corresponds to model selection)
    - topic: which topic to focus on
    - number_mcq: number of MCQ questions for this task
    - number_sr: number of self-reflect questions for this task
    
    Rules:
    - Distribute questions across topics and complexity levels
    - High complexity = use NVIDIA_LARGE (GPT-OSS)
    - Medium complexity = use NVIDIA_MEDIUM (Qwen)
    - Low complexity = use NVIDIA_SMALL (Llama)
    - Balance MCQ and self-reflect questions appropriately
    - Focus on different aspects of each topic
    """
    
    user_prompt = f"""Question config: {question_config}
    Key topics: {key_topics}
    
    Create a detailed generation plan:"""
    
    try:
        # Use NVIDIA_MEDIUM (Qwen) for planning and reasoning
        response = await generate_answer_with_model(
            selection={"provider": "qwen", "model": NVIDIA_MEDIUM},
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator,
            user_id="system",
            context="quiz_planning"
        )
        
        plan = json.loads(response.strip())
        return plan if isinstance(plan, list) else []
        
    except Exception as e:
        logger.warning(f"[QUIZ] Failed to create plan: {e}")
        # Fallback plan
        return [{
            "description": "Generate general questions",
            "complexity": "medium",
            "topic": "General",
            "number_mcq": question_config.get("mcq", 0),
            "number_sr": question_config.get("sr", 0)
        }]


async def generate_questions_and_answers(plan: List[Dict], document_summaries: str, nvidia_rotator) -> List[Dict]:
    """Generate questions and answers based on the plan using async optimization"""
    all_questions = []
    
    # Group tasks by complexity for efficient model usage
    high_complexity_tasks = [task for task in plan if task.get("complexity") == "high"]
    medium_complexity_tasks = [task for task in plan if task.get("complexity") == "medium"]
    low_complexity_tasks = [task for task in plan if task.get("complexity") == "low"]
    
    # Generate questions concurrently for each complexity level
    tasks = []
    
    # High complexity tasks (use NVIDIA_LARGE)
    for task in high_complexity_tasks:
        tasks.append(generate_task_questions(task, document_summaries, nvidia_rotator, "high"))
    
    # Medium complexity tasks (use NVIDIA_MEDIUM)
    for task in medium_complexity_tasks:
        tasks.append(generate_task_questions(task, document_summaries, nvidia_rotator, "medium"))
    
    # Low complexity tasks (use NVIDIA_SMALL)
    for task in low_complexity_tasks:
        tasks.append(generate_task_questions(task, document_summaries, nvidia_rotator, "low"))
    
    # Execute all tasks concurrently
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"[QUIZ] Task generation failed: {result}")
                continue
            if isinstance(result, list):
                all_questions.extend(result)
                
    except Exception as e:
        logger.error(f"[QUIZ] Concurrent question generation failed: {e}")
        # Fallback to sequential generation
        for task in plan:
            try:
                questions = await generate_task_questions(task, document_summaries, nvidia_rotator)
                all_questions.extend(questions)
            except Exception as task_error:
                logger.warning(f"[QUIZ] Failed to generate questions for task: {task_error}")
                continue
    
    return all_questions


async def generate_task_questions(task: Dict, document_summaries: str, nvidia_rotator, complexity: str = None) -> List[Dict]:
    """Generate questions for a specific task using appropriate model based on complexity"""
    system_prompt = f"""You are an expert quiz question generator.
    Generate {task.get('number_mcq', 0)} multiple choice questions and {task.get('number_sr', 0)} self-reflection questions.
    
    For MCQ questions:
    - Create clear, well-structured questions
    - Provide 4 answer options (A, B, C, D)
    - Mark the correct answer
    - Make distractors plausible but incorrect
    - Focus on the specific topic: {task.get('topic', 'General')}
    
    For self-reflection questions:
    - Create open-ended questions that require critical thinking
    - Focus on analysis, evaluation, and synthesis
    - Encourage personal reflection and application
    - Relate to the specific topic: {task.get('topic', 'General')}
    
    Return a JSON array of question objects with this format:
    {{
        "type": "mcq" or "self_reflect",
        "question": "question text",
        "options": ["option1", "option2", "option3", "option4"] (for MCQ only),
        "correct_answer": 0 (index for MCQ, null for self_reflect),
        "topic": "topic name",
        "complexity": "high/medium/low"
    }}
    """
    
    user_prompt = f"""Task: {task}
    Document content: {document_summaries[:4000]}...
    
    Generate questions:"""
    
    try:
        # Use appropriate model based on complexity
        if complexity == "high" or task.get("complexity") == "high":
            model_selection = {"provider": "nvidia_large", "model": NVIDIA_LARGE}
        elif complexity == "medium" or task.get("complexity") == "medium":
            model_selection = {"provider": "qwen", "model": NVIDIA_MEDIUM}
        else:
            model_selection = {"provider": "nvidia", "model": NVIDIA_SMALL}
        
        response = await generate_answer_with_model(
            selection=model_selection,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator,
            user_id="system",
            context="quiz_question_generation"
        )
        
        questions = json.loads(response.strip())
        return questions if isinstance(questions, list) else []
        
    except Exception as e:
        logger.warning(f"[QUIZ] Failed to generate questions for task: {e}")
        return []


async def mark_quiz_answers(questions: List[Dict], user_answers: Dict, nvidia_rotator) -> Dict:
    """Mark quiz answers and provide feedback"""
    results = {
        "questions": [],
        "total_score": 0,
        "correct_count": 0,
        "partial_count": 0,
        "incorrect_count": 0
    }
    
    for i, question in enumerate(questions):
        user_answer = user_answers.get(str(i))
        question_result = await mark_single_question(question, user_answer, nvidia_rotator)
        results["questions"].append(question_result)
        
        # Update counts
        if question_result["status"] == "correct":
            results["correct_count"] += 1
            results["total_score"] += 1
        elif question_result["status"] == "partial":
            results["partial_count"] += 1
            results["total_score"] += 0.5
        else:
            results["incorrect_count"] += 1
    
    return results


async def mark_single_question(question: Dict, user_answer: Any, nvidia_rotator) -> Dict:
    """Mark a single question"""
    result = {
        "question": question["question"],
        "type": question["type"],
        "user_answer": user_answer,
        "status": "incorrect",
        "explanation": ""
    }
    
    if question["type"] == "mcq":
        # MCQ marking
        correct_index = question.get("correct_answer", 0)
        if user_answer is not None and int(user_answer) == correct_index:
            result["status"] = "correct"
            result["explanation"] = "Correct answer!"
        else:
            result["status"] = "incorrect"
            result["explanation"] = await generate_mcq_explanation(question, user_answer, nvidia_rotator)
        
        result["correct_answer"] = correct_index
        result["options"] = question.get("options", [])
        
    elif question["type"] == "self_reflect":
        # Self-reflection marking using AI
        result["status"] = await evaluate_self_reflect_answer(question, user_answer, nvidia_rotator)
        result["explanation"] = await generate_self_reflect_feedback(question, user_answer, result["status"], nvidia_rotator)
    
    return result


async def generate_mcq_explanation(question: Dict, user_answer: Any, nvidia_rotator) -> str:
    """Generate explanation for MCQ answer using Llama model"""
    system_prompt = """You are an expert tutor. Explain why the user's answer was wrong and why the correct answer is right.
    Be concise but helpful. Focus on the key concept being tested.
    
    Provide:
    1. Why the user's answer was incorrect
    2. Why the correct answer is right
    3. Key concept or principle being tested
    4. Brief learning tip
    
    Keep it educational and encouraging."""
    
    user_prompt = f"""Question: {question['question']}
    Options: {question.get('options', [])}
    User's answer: {user_answer}
    Correct answer: {question.get('correct_answer', 0)}
    
    Explain why the user was wrong and provide learning guidance:"""
    
    try:
        response = await generate_answer_with_model(
            selection={"provider": "nvidia", "model": NVIDIA_SMALL},
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator,
            user_id="system",
            context="quiz_explanation"
        )
        return response
    except Exception as e:
        logger.warning(f"[QUIZ] Failed to generate MCQ explanation: {e}")
        return "The correct answer is different from your choice. Please review the material."


async def evaluate_self_reflect_answer(question: Dict, user_answer: str, nvidia_rotator) -> str:
    """Evaluate self-reflection answer using Llama model"""
    system_prompt = """You are an expert educator evaluating student responses.
    Evaluate the student's answer and determine if it's correct, partially correct, or incorrect.
    
    Criteria:
    - "correct": Answer demonstrates clear understanding, addresses the question fully, shows critical thinking
    - "partial": Answer shows some understanding but incomplete, partially addresses the question
    - "incorrect": Answer shows misunderstanding, doesn't address the question, or is too brief
    
    Return only one word: "correct", "partial", or "incorrect"
    """
    
    user_prompt = f"""Question: {question['question']}
    Student's answer: {user_answer or 'No answer provided'}
    
    Evaluate the answer:"""
    
    try:
        response = await generate_answer_with_model(
            selection={"provider": "nvidia", "model": NVIDIA_SMALL},
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator,
            user_id="system",
            context="quiz_evaluation"
        )
        
        response = response.strip().lower()
        if response in ["correct", "partial", "incorrect"]:
            return response
        else:
            return "partial"  # Default to partial if unclear
            
    except Exception as e:
        logger.warning(f"[QUIZ] Failed to evaluate self-reflect answer: {e}")
        return "partial"


async def generate_self_reflect_feedback(question: Dict, user_answer: str, status: str, nvidia_rotator) -> str:
    """Generate feedback for self-reflection answer using Llama model"""
    system_prompt = """You are an expert tutor providing feedback on student responses.
    Provide constructive feedback that helps the student understand their answer and improve.
    Be encouraging but honest about areas for improvement.
    
    For each status:
    - "correct": Acknowledge strengths and encourage continued learning
    - "partial": Point out what's good, suggest improvements, encourage deeper thinking
    - "incorrect": Gently guide toward correct understanding, provide hints, encourage retry
    
    Keep feedback concise but helpful."""
    
    user_prompt = f"""Question: {question['question']}
    Student's answer: {user_answer or 'No answer provided'}
    Evaluation: {status}
    
    Provide constructive feedback:"""
    
    try:
        response = await generate_answer_with_model(
            selection={"provider": "nvidia", "model": NVIDIA_SMALL},
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator,
            user_id="system",
            context="quiz_feedback"
        )
        return response
    except Exception as e:
        logger.warning(f"[QUIZ] Failed to generate self-reflect feedback: {e}")
        return "Thank you for your response. Please review the material for a more complete answer."
