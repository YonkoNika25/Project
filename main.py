"""
Main Demo Script - End-to-End Tutoring Pipeline with Real LLM.

Requires HF_TOKEN environment variable.
Usage: python main.py
"""
import os
import logging
import sys

# Ensure src is in path
sys.path.append(os.path.abspath("."))

from src.models import (
    ProblemRecord,
    DiagnosisResult,
    ReferenceSolution,
)
from src.solver.qwen_client import QwenSolverClient # Optional, we can use adapter directly
from src.checker.answer_checker import check_answer
from src.diagnosis.engine import diagnose
from src.hint.controller import HintController
from src.utils.llm_client import hf_llm_adapter

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def run_tutor_demo():
    # 0. Check for API Token
    if "HF_TOKEN" not in os.environ:
        print("ERROR: Please set the HF_TOKEN environment variable.")
        print("Example (Windows PowerShell): $env:HF_TOKEN='your_token_here'")
        return

    # 1. Input Problem (GSM8K Style)
    problem_text = "Jan has 3 apples. She buys 5 more apples. How many apples does Jan have now?"
    gold_answer = "#### 8" # GSM8K format
    student_answer_raw = "She has 6 apples." # Wrong answer for demo
    
    print(f"--- PROBLEM ---\n{problem_text}")
    print(f"--- STUDENT ANSWER ---\n{student_answer_raw}\n")

    # 2. Reference Solution (Using real LLM)
    print("Step 1: Generating Reference Solution...")
    # For a simple demo, we can simulate the ReferenceSolution object 
    # OR use the hf_llm_adapter to actually solve it.
    # Let's use the adapter to keep it simple but "real".
    solve_prompt = f"Solve this math problem and provide the numeric answer at the end preceded by '#### '.\n\nProblem: {problem_text}"
    raw_solve = hf_llm_adapter(solve_prompt)
    
    # Normally we'd use solver/reference_parser, but let's mock the struct for now
    # to ensure the pipeline continues even if parser is sensitive to text formats
    ref_sol = ReferenceSolution(
        final_answer=8.0, 
        solution_text=raw_solve,
        confidence=1.0,
        schema_version="1.0",
        source="qwen-hf"
    )
    print(f"Reference Answer: {ref_sol.final_answer}\n")

    # 3. Answer Checking
    print("Step 2: Checking Student Answer...")
    check_res = check_answer(student_answer_raw, ref_sol.final_answer)
    print(f"Correctness: {check_res.correctness.value}")
    print(f"Normalized Student Value: {check_res.student_value}\n")

    if check_res.correctness.value == "correct":
        print("Student is correct! No hint needed.")
        return

    # 4. Diagnosis (Using real LLM)
    print("Step 3: Diagnosing Student Error...")
    # Note: diagnose() takes llm_callable as a kwarg
    diag_res = diagnose(
        problem_text=problem_text,
        reference_solution_text=ref_sol.solution_text,
        reference_answer=ref_sol.final_answer,
        student_raw=student_answer_raw,
        check_result=check_res,
        llm_callable=hf_llm_adapter
    )
    print(f"Error Label: {diag_res.label.value}")
    print(f"Explanation: {diag_res.explanation}\n")

    # 5. Hint Generation (Using real LLM)
    print("Step 4: Generating Pedagogical Hint...")
    # HintController coordinates generation, verification, and fallback
    hint_controller = HintController(llm_callable=hf_llm_adapter)
    hint_res = hint_controller.get_hint(
        problem_text=problem_text,
        reference_solution_text=ref_sol.solution_text,
        reference_answer=ref_sol.final_answer,
        student_raw=student_answer_raw,
        diagnosis=diag_res
    )

    print("--- FINAL RESULT ---")
    print(f"Hint Level: {hint_res.hint_level.value}")
    print(f"Hint Text: {hint_res.hint_text}")
    print(f"Verification Info: Spoiler-free? {'Yes' if not hint_res.fallback_used else 'Fallback Used'}")

if __name__ == "__main__":
    run_tutor_demo()
