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
    SolverResponse,
    SolverStatus,
)
from src.solver.reference_parser import parse_solver_response, ParseStatus
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
    student_answer_raw = "She has 6 apples." # Wrong answer for demo
    
    print(f"--- PROBLEM ---\n{problem_text}")
    print(f"--- STUDENT ANSWER ---\n{student_answer_raw}\n")

    # 2. Reference Solution (Using real LLM + parser)
    print("Step 1: Generating Reference Solution...")
    solve_prompt = f"Solve this math problem and provide the numeric answer at the end preceded by '#### '.\n\nProblem: {problem_text}"
    raw_solve = hf_llm_adapter(solve_prompt)

    solver_response = SolverResponse(
        raw_text=raw_solve,
        status=SolverStatus.SUCCESS,
        model_name="Qwen/Qwen2.5-Math-7B-Instruct",
        latency_ms=0.0,
        attempt_count=1,
    )
    parse_result = parse_solver_response(solver_response)
    if parse_result.status != ParseStatus.SUCCESS or parse_result.reference is None:
        print("ERROR: Failed to parse reference answer from solver output.")
        print(f"Parse status: {parse_result.status.value}")
        print(f"Details: {parse_result.error_message}")
        print("Raw solver output:")
        print(raw_solve)
        return

    ref_sol = parse_result.reference
    print(f"Parser status: {parse_result.status.value}")
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
