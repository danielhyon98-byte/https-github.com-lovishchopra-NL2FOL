import time, z3
print("z3py version:", z3.get_version_string())
# 1. entailment: x>y, y>z |= x>z over Int
s = z3.Solver(); s.set("timeout", 2000)
x,y,zz = z3.Ints("x y z"); z = zz
prem = [x>y, y>z]
s.add(prem); c1 = s.check(); print("premises consistent:", c1)
s.push(); s.add(z3.Not(x>zz)); t=time.perf_counter(); r=s.check(); print("entailment (expect unsat):", r, f"{(time.perf_counter()-t)*1000:.1f}ms"); s.pop()
# 2. counterexample: x>y |= x>y+1 ? no
s2 = z3.Solver(); s2.add(x>y); s2.add(z3.Not(x>y+1)); r=s2.check(); print("counterexample case (expect sat):", r, s2.model() if r==z3.sat else None)
# 3. inconsistent premises
s3 = z3.Solver(); s3.add(x>0, x<0); print("inconsistent premises (expect unsat):", s3.check())
# 4. Int vs Real distinction: 2*x == 1
s4 = z3.Solver(); s4.add(2*x==1); print("2x=1 over Int (expect unsat):", s4.check())
rx = z3.Real("rx"); s5 = z3.Solver(); s5.add(2*rx==1); print("2x=1 over Real (expect sat):", s5.check(), s5.model())
# 5. timeout behaviour -> unknown
s6 = z3.Solver(); s6.set("timeout", 50)
a,b,c = z3.Ints("a b c")
s6.add(a>0,b>0,c>0, a**3+b**3==c**3, c<10**9)  # nonlinear, likely unknown/timeout
t=time.perf_counter(); r=s6.check(); print("nonlinear with 50ms timeout:", r, s6.reason_unknown() if r==z3.unknown else "", f"{(time.perf_counter()-t)*1000:.1f}ms")
# 6. quantifier
f = z3.Function("f", z3.IntSort(), z3.IntSort())
s7 = z3.Solver(); s7.set("timeout", 2000); s7.add(z3.ForAll([x], f(x) > x)); s7.add(z3.Not(f(5) > 5)); print("quantified entailment (expect unsat):", s7.check())
