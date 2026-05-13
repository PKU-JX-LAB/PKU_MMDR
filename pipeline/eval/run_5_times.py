import sys
import time
from eval.run_and_eval import run_loop

def main():
    target_success = 5
    consecutive_success = 0
    total_runs = 0
    
    while consecutive_success < target_success:
        total_runs += 1
        print(f"\n\n{'='*50}")
        print(f"=== STARTING RUN {total_runs} (Consecutive Successes: {consecutive_success}/{target_success}) ===")
        print(f"{'='*50}\n")
        
        try:
            score = run_loop()
        except Exception as e:
            print(f"Exception during run_loop: {e}")
            score = 0.0

        if score >= 4.0:
            consecutive_success += 1
            print(f"\n>>> RUN {total_runs} SUCCESS! Score: {score:.3f}. Consecutive count: {consecutive_success}/{target_success} <<<\n")
        else:
            print(f"\n>>> RUN {total_runs} FAILED! Score: {score:.3f}. Resetting consecutive count to 0 <<<\n")
            # The prompt says: "If the test score is below 4, do not stop refining the
            # innovation points; if the score does not reach 4, do not terminate the task."
            # Which means if it fails, I should stop this loop and modify code.
            # I will exit with error code 1, so Trae knows to modify code.
            sys.exit(1)
            
    print(f"\n\n{'='*50}")
    print(f"=== ALL {target_success} CONSECUTIVE RUNS COMPLETED SUCCESSFULLY! ===")
    print(f"{'='*50}\n")
    sys.exit(0)

if __name__ == "__main__":
    main()
