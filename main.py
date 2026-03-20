"""
Main Demo Script - End-to-End Tutoring Pipeline with Real LLM.

Requires OPENROUTER_API_KEY environment variable.
Usage: python main.py
"""
import os
import logging
import sys

# Ensure src is in path
sys.path.append(os.path.abspath("."))

from src.solver.reference_parser import parse_solver_response, ParseStatus
from src.solver.qwen_client import QwenSolverClient, build_solver_config_from_env
from src.checker.answer_checker import check_answer
from src.diagnosis.engine import diagnose
from src.verification.symbolic_state_builder import build_symbolic_state
from src.verification.symbolic_verifier import verify_symbolic_consistency
from src.hint.controller import HintController
from src.utils.llm_client import openrouter_llm_adapter

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
try:
    # Prevent UnicodeEncodeError on Windows terminals when hints contain Vietnamese text.
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def run_tutor_demo():
    # 0. Check for API Token
    if "OPENROUTER_API_KEY" not in os.environ:
        print("ERROR: Please set the OPENROUTER_API_KEY environment variable.")
        print("Example (Windows PowerShell): $env:OPENROUTER_API_KEY='your_token_here'")
        return

    # 1. Input Problem (GSM8K Style)
    problem_text = "A concert ticket costs $40. Mr. Benson bought 12 tickets and received a 5% discount for every ticket bought that exceeds 10. How much did Mr. Benson pay in all?"
    student_answer_raw = "Answer is 516." # Wrong answer for demo
    
    print(f"--- PROBLEM ---\n{problem_text}")
    print(f"--- STUDENT ANSWER ---\n{student_answer_raw}\n")

    # 2. Reference Solution (Using real LLM + parser)
    print("Step 1: Generating Reference Solution...")
    solver_client = QwenSolverClient(config=build_solver_config_from_env())
    try:
        solver_response = solver_client.solve(problem_text)
    finally:
        solver_client.close()

    parse_result = parse_solver_response(solver_response)
    if parse_result.status != ParseStatus.SUCCESS or parse_result.reference is None:
        print("ERROR: Failed to parse reference answer from solver output.")
        print(f"Parse status: {parse_result.status.value}")
        print(f"Details: {parse_result.error_message}")
        print("Raw solver output:")
        print(solver_response.raw_text or solver_response.error_message)
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

    # 4. Build Phase 2 symbolic evidence
    print("Step 3: Building Symbolic Evidence...")
    symbolic_state = build_symbolic_state(problem_text, ref_sol.solution_text)
    verification_result = verify_symbolic_consistency(symbolic_state, check_res)
    print(f"Verifier status: {verification_result.status.value}")

    # 5. Diagnosis (rule + symbolic evidence + LLM fallback)
    print("Step 4: Diagnosing Student Error...")
    diag_res = diagnose(
        problem_text=problem_text,
        reference_solution_text=ref_sol.solution_text,
        reference_answer=ref_sol.final_answer,
        student_raw=student_answer_raw,
        check_result=check_res,
        llm_callable=openrouter_llm_adapter,
        symbolic_state=symbolic_state,
        verification_result=verification_result,
    )
    print(f"Error Label: {diag_res.label.value}")
    print(f"Explanation: {diag_res.explanation}\n")

    # 6. Hint Generation (Using real LLM)
    print("Step 5: Generating Pedagogical Hint...")
    # HintController coordinates generation, verification, and fallback
    hint_controller = HintController(llm_callable=openrouter_llm_adapter)
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
    if hint_res.attempted_hints:
        print("\n--- HINT ATTEMPTS FROM MODEL ---")
        for idx, attempted_hint in enumerate(hint_res.attempted_hints, start=1):
            print(f"Attempt {idx}: {attempted_hint}")
    if hint_res.verification_notes:
        print("\n--- HINT VERIFICATION NOTES ---")
        for note in hint_res.verification_notes:
            print(f"- {note}")

if __name__ == "__main__":
    run_tutor_demo()
