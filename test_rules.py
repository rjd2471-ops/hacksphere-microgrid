from app import dispatch

assert dispatch(160, 12) == ("Main Grid", False)          # exactly 160 is not above 160
assert dispatch(160.1, 12) == ("Renewable Storage", False)
assert dispatch(100, 17) == ("Main Grid", False)
assert dispatch(100, 18) == ("Renewable Storage", False)  # window starts at 18
assert dispatch(100, 22) == ("Renewable Storage", False)  # 22 is inclusive
assert dispatch(100, 23) == ("Main Grid", False)
assert dispatch(200, 12) == ("Renewable Storage", True)   # overload at 200
assert dispatch(199.9, 3) == ("Renewable Storage", False)
print("All rule tests passed")
