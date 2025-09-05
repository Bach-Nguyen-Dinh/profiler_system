import cProfile
import time

def slow_function():
    total = 0
    for i in range(1000000):
        total += i
    return total

def fast_function():
    return sum(range(1000000))

def main():
    slow_function()
    fast_function()

    x = 1
    x += 1
    print(x)

if __name__ == "__main__":
    # Run the profiler on main()
    cProfile.run("main()")
