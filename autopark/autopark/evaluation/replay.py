import argparse
from autopark.storage.run_store import replay_run


def main():
    parser = argparse.ArgumentParser(description="Chạy lại snapshot và đối chiếu kết quả mô phỏng")
    parser.add_argument("run_directory")
    args = parser.parse_args()
    session = replay_run(args.run_directory)
    print(f"Replay OK: {session.state.value}, {session.world.step_count} steps")
    session.close()


if __name__ == "__main__":
    main()
