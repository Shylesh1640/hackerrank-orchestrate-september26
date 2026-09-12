import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pipeline import main

if __name__ == "__main__":
    main()