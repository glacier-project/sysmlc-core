from pathlib import Path

import syside

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "ice-lab"


def main() -> None:
    """Load the SysML model and print a summary of its elements."""
    sysml_files = syside.collect_files_recursively(str(MODEL_DIR))
    print(f"Found {len(sysml_files)} SysML files:")
    for f in sysml_files:
        print(f"  {f}")
    print()

    _model, diagnostics = syside.try_load_model(paths=sysml_files)
    print(f"Diagnostics: {diagnostics}")
    print()


if __name__ == "__main__":
    main()
