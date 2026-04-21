from __future__ import annotations

import os

from german_public_receipts_chain_eval import main


ACTIVE_CHAINS = "REWE,PENNY,dm"


if __name__ == "__main__":
    os.environ.setdefault("LIDLTOOL_GERMAN_PUBLIC_CHAINS", ACTIVE_CHAINS)
    os.environ.setdefault("LIDLTOOL_GERMAN_PUBLIC_EVAL_OUTPUT_DIR", "german_active_receipts_chain_eval")
    main()
