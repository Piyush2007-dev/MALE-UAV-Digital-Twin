def get_fault_targets(fault_mode: str) -> dict:
    if fault_mode == "misfire":
        return {"wear": 0.5, "egt": 60.0, "cht": 0.0, "kurt": 0.0, "op": 0.0, "rpm": 220.0, "map": 3.0}
    elif fault_mode == "cooling":
        return {"wear": 0.3, "egt": 0.0, "cht": 35.0, "kurt": 0.0, "op": 12.0, "rpm": 0.0, "map": 0.0}
    elif fault_mode == "bearing":
        return {"wear": 0.4, "egt": 0.0, "cht": 0.0, "kurt": 3.2, "op": 0.0, "rpm": 0.0, "map": 0.0}
    else:
        return {"wear": 0.0005, "egt": 0.0, "cht": 0.0, "kurt": 0.0, "op": 0.0, "rpm": 0.0, "map": 0.0}
