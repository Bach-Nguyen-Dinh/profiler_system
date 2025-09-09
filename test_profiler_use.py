import cProfile
import psutil
import threading
import time
import tracemalloc
import sys
from collections import defaultdict
import os
from datetime import datetime

class AutomaticProfiler:
    def __init__(self):
        self.function_stats = defaultdict(lambda: {
            'calls': 0,
            'total_time': 0,
            'cpu_cores_used': set(),
            'cpu_usage_samples': [],
            'memory_peak': 0,
            'memory_samples': [],
            'call_stack': [],
            'call_history': []  # NEW: Store individual call timestamps
        })
        self.monitoring = False
        self.monitor_thread = None
        self.call_stack = []
        self.original_trace = None
        self.all_calls = []  # NEW: Store all function calls with timestamps
        
    def start_monitoring(self):
        """Start automatic function call tracing and resource monitoring"""
        self.monitoring = True
        
        # Start memory tracking
        tracemalloc.start()
        
        # Start background resource monitoring
        self.monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self.monitor_thread.start()
        
        # Set up function call tracing
        self.original_trace = sys.gettrace()
        sys.settrace(self._trace_calls)
        
        print("Automatic profiling started...")
        
    def stop_monitoring(self):
        """Stop automatic tracing and monitoring"""
        self.monitoring = False
        
        # Stop function call tracing
        sys.settrace(self.original_trace)
        
        # Stop background monitoring
        if self.monitor_thread:
            self.monitor_thread.join()
            
        # Stop memory tracking
        tracemalloc.stop()
        
        print("Automatic profiling stopped.")
    
    def _trace_calls(self, frame, event, arg):
        """Trace function calls automatically"""
        if event == 'call':
            func_name = self._get_function_name(frame)
            
            # Skip internal/system functions
            if self._should_skip_function(func_name):
                return self._trace_calls
                
            # Record function entry with timestamp
            start_timestamp = datetime.now()
            call_info = {
                'name': func_name,
                'start_time': time.perf_counter(),
                'start_timestamp': start_timestamp,  # NEW: Actual timestamp
                'start_memory': tracemalloc.get_traced_memory()[0] if tracemalloc.is_tracing() else 0
            }
            self.call_stack.append(call_info)
            self.function_stats[func_name]['calls'] += 1
            
        elif event == 'return':
            if self.call_stack:
                call_info = self.call_stack.pop()
                func_name = call_info['name']
                
                # Calculate execution time
                end_time = time.perf_counter()
                end_timestamp = datetime.now()  # NEW: End timestamp
                execution_time = end_time - call_info['start_time']
                self.function_stats[func_name]['total_time'] += execution_time
                
                # NEW: Store individual call record with timestamps
                call_record = {
                    'function': func_name,
                    'start_timestamp': call_info['start_timestamp'],
                    'end_timestamp': end_timestamp,
                    'duration_ms': execution_time * 1000,  # Convert to milliseconds
                    'start_time_formatted': call_info['start_timestamp'].strftime("%H:%M:%S.%f")[:-3],
                    'end_time_formatted': end_timestamp.strftime("%H:%M:%S.%f")[:-3]
                }
                
                self.function_stats[func_name]['call_history'].append(call_record)
                self.all_calls.append(call_record)
                
                # Calculate memory usage for this call
                if tracemalloc.is_tracing():
                    current_memory = tracemalloc.get_traced_memory()[0]
                    memory_used = (current_memory - call_info['start_memory']) / 1024 / 1024  # MB
                    if memory_used > 0:
                        self.function_stats[func_name]['memory_samples'].append(memory_used)
        
        return self._trace_calls
    
    def _get_function_name(self, frame):
        """Extract meaningful function name from frame"""
        filename = frame.f_code.co_filename
        func_name = frame.f_code.co_name
        
        # Get just the filename without path
        base_filename = os.path.basename(filename)
        
        # Create readable function identifier
        return f"{base_filename}:{func_name}"
    
    def _should_skip_function(self, func_name):
        """Determine if we should skip tracking this function"""
        skip_patterns = [
            '<frozen',  # Built-in modules
            'threading.py',
            'psutil',
            '_trace_calls',
            '_monitor_resources',
            'settrace',
            'gettrace'
        ]
        
        for pattern in skip_patterns:
            if pattern in func_name:
                return True
        return False
    
    def _monitor_resources(self):
        """Background thread to monitor CPU and memory usage"""
        process = psutil.Process()
        
        while self.monitoring:
            try:
                # Get CPU info
                cpu_percent = process.cpu_percent()
                try:
                    cpu_affinity = process.cpu_affinity()
                except (AttributeError, psutil.AccessDenied):
                    cpu_affinity = list(range(psutil.cpu_count()))
                
                # Get memory info
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024  # Convert to MB
                
                # Record stats for functions currently executing
                for call_info in self.call_stack:
                    func_name = call_info['name']
                    if not self._should_skip_function(func_name):
                        stats = self.function_stats[func_name]
                        stats['cpu_cores_used'].update(cpu_affinity)
                        stats['cpu_usage_samples'].append(cpu_percent)
                        stats['memory_peak'] = max(stats['memory_peak'], memory_mb)
                
                time.sleep(0.01)  # Sample every 10ms
                
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
    
    def get_cpu_core_info(self):
        """Get detailed CPU core information"""
        cpu_count = psutil.cpu_count(logical=False)  # Physical cores
        cpu_count_logical = psutil.cpu_count(logical=True)  # Logical cores
        
        try:
            cpu_freq = psutil.cpu_freq()
            freq_info = cpu_freq._asdict() if cpu_freq else None
        except:
            freq_info = None
        
        return {
            'physical_cores': cpu_count,
            'logical_cores': cpu_count_logical,
            'frequency': freq_info
        }
    
    def print_detailed_report(self):
        """Print comprehensive profiling report"""
        print("\n" + "="*80)
        print("AUTOMATIC PROFILING REPORT")
        print("="*80)
        
        # System info
        cpu_info = self.get_cpu_core_info()
        print(f"\nSYSTEM INFO:")
        print(f"Physical CPU Cores: {cpu_info['physical_cores']}")
        print(f"Logical CPU Cores: {cpu_info['logical_cores']}")
        if cpu_info['frequency'] and cpu_info['frequency']['current']:
            print(f"CPU Frequency: {cpu_info['frequency']['current']:.2f} MHz")
        
        print(f"\nFUNCTION PERFORMANCE BREAKDOWN:")
        print("-" * 80)
        
        # Filter out very short functions and sort by total time
        significant_functions = {
            name: stats for name, stats in self.function_stats.items()
            if stats['total_time'] > 0.001  # Only show functions taking > 1ms
        }
        
        sorted_functions = sorted(
            significant_functions.items(), 
            key=lambda x: x[1]['total_time'], 
            reverse=True
        )
        
        for func_name, stats in sorted_functions:
            print(f"\nFunction: {func_name}")
            print(f"  Calls: {stats['calls']}")
            print(f"  Total Time: {stats['total_time']:.6f} seconds")
            print(f"  Avg Time/Call: {stats['total_time']/stats['calls']:.6f} seconds")
            
            # CPU info
            if stats['cpu_cores_used']:
                cores_list = sorted(list(stats['cpu_cores_used']))
                print(f"  CPU Cores Used: {cores_list}")
            
            if stats['cpu_usage_samples']:
                avg_cpu = sum(stats['cpu_usage_samples']) / len(stats['cpu_usage_samples'])
                max_cpu = max(stats['cpu_usage_samples'])
                print(f"  CPU Usage: {avg_cpu:.1f}% avg, {max_cpu:.1f}% peak")
            
            # Memory info
            if stats['memory_samples']:
                avg_memory = sum(stats['memory_samples']) / len(stats['memory_samples'])
                print(f"  Memory Usage: {avg_memory:.2f} MB avg")
            
            if stats['memory_peak'] > 0:
                print(f"  Memory Peak: {stats['memory_peak']:.2f} MB")

    def print_call_timeline(self):
        """NEW: Print detailed timeline of all function calls with timestamps"""
        print("\n" + "="*80)
        print("FUNCTION CALL TIMELINE")
        print("="*80)
        
        if not self.all_calls:
            print("No function calls recorded.")
            return
        
        # Sort calls by start timestamp
        sorted_calls = sorted(self.all_calls, key=lambda x: x['start_timestamp'])
        
        print(f"{'Start Time':<15} {'End Time':<15} {'Duration (ms)':<12} {'Function'}")
        print("-" * 80)
        
        for call in sorted_calls:
            print(f"{call['start_time_formatted']:<15} "
                  f"{call['end_time_formatted']:<15} "
                  f"{call['duration_ms']:<12.3f} "
                  f"{call['function']}")
    
    def print_function_call_details(self, function_name=None):
        """NEW: Print detailed call history for specific functions or all functions"""
        print("\n" + "="*80)
        print("DETAILED FUNCTION CALL HISTORY")
        print("="*80)
        
        if function_name:
            if function_name in self.function_stats:
                self._print_function_calls(function_name, self.function_stats[function_name])
            else:
                print(f"Function '{function_name}' not found.")
        else:
            # Print details for all significant functions
            significant_functions = {
                name: stats for name, stats in self.function_stats.items()
                if stats['total_time'] > 0.001 and stats['call_history']
            }
            
            for func_name, stats in significant_functions.items():
                self._print_function_calls(func_name, stats)
    
    def _print_function_calls(self, func_name, stats):
        """Helper method to print call details for a specific function"""
        print(f"\n{func_name}:")
        print(f"  Total calls: {len(stats['call_history'])}")
        
        if stats['call_history']:
            print(f"  {'Call #':<8} {'Start Time':<15} {'End Time':<15} {'Duration (ms)':<12}")
            print("  " + "-" * 60)
            
            for i, call in enumerate(stats['call_history'], 1):
                print(f"  {i:<8} "
                      f"{call['start_time_formatted']:<15} "
                      f"{call['end_time_formatted']:<15} "
                      f"{call['duration_ms']:<12.3f}")

# Create global profiler instance
profiler = AutomaticProfiler()

# Your existing functions - NO DECORATORS NEEDED!
def slow_function():
    total = 0
    for i in range(1000000):
        total += i
    return total

def fast_function():
    return sum(range(1000000))

def memory_intensive_function():
    # Create a large list to demonstrate memory usage
    large_list = [i**2 for i in range(100000)]
    return sum(large_list)

def main():
    # Run your functions - they will be automatically profiled
    slow_function()
    fast_function()
    memory_intensive_function()
    
    x = 1
    x += 1
    print(x)

if __name__ == "__main__":
    # Start monitoring
    profiler.start_monitoring()
    
    try:
        # Run main
        main()
        
        # Also run traditional cProfile for comparison
        print("\nTraditional cProfile output:")
        cProfile.run("main()")
        
    finally:
        # Stop monitoring and show detailed reports
        profiler.stop_monitoring()
        profiler.print_detailed_report()
        
        # NEW: Print timeline and detailed call information
        profiler.print_call_timeline()
        profiler.print_function_call_details()