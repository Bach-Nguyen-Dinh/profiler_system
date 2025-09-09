import cProfile
import psutil
import threading
import time
import tracemalloc
import sys
import csv
import os
import atexit
from collections import defaultdict
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

@dataclass
class SystemMetricsSample:
    """Single system metrics sample at a specific timestamp"""
    timestamp: datetime
    timestamp_formatted: str
    cpu_usage: float
    memory_usage: float
    total_memory: int
    swap_usage: float
    total_swap: int
    per_core_usage: Dict[str, float]
    per_core_freq: Dict[str, float]
    cpu_temperature: Optional[float]
    cpu_power: Optional[float]
    current_function: Optional[str]  # Function executing at this timestamp
    function_type: str  # 'main', 'other', or 'idle'

class IntegratedProfiler:
    def __init__(self):
        # Function tracking
        self.function_stats = defaultdict(lambda: {
            'calls': 0,
            'total_time': 0,
            'call_history': [],
            'attributed_metrics': []  # List of SystemMetricsSample objects
        })
        
        # System metrics tracking
        self.metrics_samples = []  # All 1ms samples
        self.main_function_metrics = []  # Samples attributed to main functions
        self.other_function_metrics = []  # Samples attributed to other functions
        self.whole_system_metrics = []  # All samples (same as metrics_samples)
        
        # Control variables
        self.monitoring = False
        self.monitor_thread = None
        self.call_stack = []
        self.original_trace = None
        
        # Configuration
        self.main_function_patterns = [
            'slow_function',
            'fast_function', 
            'memory_intensive_function',
            'main'
        ]  # Define which functions are considered "main functions"
        
        self.metrics_interval = 0.001  # 1ms sampling interval
        
        # CSV output
        self._csv_file = None
        atexit.register(self._save_metrics_to_csv)
        
    def add_main_function_pattern(self, pattern: str):
        """Add a function name pattern to be considered as 'main function'"""
        self.main_function_patterns.append(pattern)
    
    def start_monitoring(self):
        """Start automatic function call tracing and system metrics monitoring"""
        self.monitoring = True
        
        # Initialize CSV file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._csv_file = f"integrated_metrics_{timestamp}.csv"
        
        # Start memory tracking
        tracemalloc.start()
        
        # Start system metrics monitoring (1ms intervals)
        self.monitor_thread = threading.Thread(target=self._monitor_system_metrics, daemon=True)
        self.monitor_thread.start()
        
        # Set up function call tracing
        self.original_trace = sys.gettrace()
        sys.settrace(self._trace_calls)
        
        print(f"Integrated profiling started (1ms sampling)...")
        print(f"Metrics will be saved to: {self._csv_file}")
        
    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring = False
        
        # Stop function call tracing
        sys.settrace(self.original_trace)
        
        # Stop background monitoring
        if self.monitor_thread:
            self.monitor_thread.join()
            
        # Stop memory tracking
        tracemalloc.stop()
        
        # Save final data
        self._save_metrics_to_csv()
        
        print("Integrated profiling stopped.")
    
    def _trace_calls(self, frame, event, arg):
        """Trace function calls automatically"""
        if event == 'call':
            func_name = self._get_function_name(frame)
            
            # Skip internal/system functions for tracing, but still track them
            if not self._should_skip_function(func_name):
                start_timestamp = datetime.now()
                call_info = {
                    'name': func_name,
                    'start_time': time.perf_counter(),
                    'start_timestamp': start_timestamp,
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
                end_timestamp = datetime.now()
                execution_time = end_time - call_info['start_time']
                self.function_stats[func_name]['total_time'] += execution_time
                
                # Store call record
                call_record = {
                    'function': func_name,
                    'start_timestamp': call_info['start_timestamp'],
                    'end_timestamp': end_timestamp,
                    'duration_ms': execution_time * 1000,
                    'start_time_formatted': call_info['start_timestamp'].strftime("%H:%M:%S.%f")[:-3],
                    'end_time_formatted': end_timestamp.strftime("%H:%M:%S.%f")[:-3]
                }
                
                self.function_stats[func_name]['call_history'].append(call_record)
        
        return self._trace_calls
    
    def _get_function_name(self, frame):
        """Extract meaningful function name from frame"""
        filename = frame.f_code.co_filename
        func_name = frame.f_code.co_name
        base_filename = os.path.basename(filename)
        return f"{base_filename}:{func_name}"
    
    def _should_skip_function(self, func_name):
        """Determine if we should skip tracking this function"""
        skip_patterns = [
            '<frozen',
            'threading.py',
            'psutil',
            '_trace_calls',
            '_monitor_system_metrics',
            '_get_system_metrics',
            'settrace',
            'gettrace'
        ]
        
        for pattern in skip_patterns:
            if pattern in func_name:
                return True
        return False
    
    def _is_main_function(self, func_name):
        """Check if function is considered a 'main' function"""
        if func_name is None:
            return False
        
        for pattern in self.main_function_patterns:
            if pattern in func_name:
                return True
        return False
    
    def _get_current_executing_function(self):
        """Get the currently executing function from call stack"""
        if self.call_stack:
            return self.call_stack[-1]['name']  # Top of stack
        return None
    
    def _get_system_metrics(self):
        """Get current system metrics (optimized for 1ms sampling)"""
        try:
            # Get basic CPU and memory info
            cpu_usage = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # Get per-core info (this might be expensive at 1ms)
            per_core_usage = {}
            per_core_freq = {}
            
            try:
                per_core_cpu = psutil.cpu_percent(interval=None, percpu=True)
                per_core_usage = {f"core_{i}_usage": usage for i, usage in enumerate(per_core_cpu)}
            except:
                pass
            
            try:
                if hasattr(psutil, "cpu_freq"):
                    freq_info = psutil.cpu_freq(percpu=True)
                    if freq_info:
                        per_core_freq = {f"core_{i}_frequency": freq.current for i, freq in enumerate(freq_info)}
            except:
                pass
            
            # Temperature and power (expensive operations - sample less frequently)
            cpu_temperature = None
            cpu_power = None
            
            # Only sample temperature/power every 100ms to reduce overhead
            if len(self.metrics_samples) % 100 == 0:
                try:
                    if hasattr(psutil, "sensors_temperatures"):
                        temp_info = psutil.sensors_temperatures()
                        if 'coretemp' in temp_info:
                            cpu_temperature = temp_info['coretemp'][0].current
                except:
                    pass
                
                try:
                    cpu_power = self._get_cpu_power()
                except:
                    pass
            
            return {
                'cpu_usage': cpu_usage,
                'memory_usage': memory.percent,
                'total_memory': memory.total,
                'swap_usage': swap.percent,
                'total_swap': swap.total,
                'per_core_usage': per_core_usage,
                'per_core_freq': per_core_freq,
                'cpu_temperature': cpu_temperature,
                'cpu_power': cpu_power,
            }
        except Exception as e:
            # Return empty metrics if there's an error
            return {
                'cpu_usage': 0,
                'memory_usage': 0,
                'total_memory': 0,
                'swap_usage': 0,
                'total_swap': 0,
                'per_core_usage': {},
                'per_core_freq': {},
                'cpu_temperature': None,
                'cpu_power': None,
            }
    
    def _get_cpu_power(self):
        """Get CPU power consumption (simplified for performance)"""
        try:
            with open("/sys/class/powercap/intel-rapl:0/energy_uj", "r") as f:
                energy1 = int(f.read().strip())
            
            time.sleep(0.01)  # 10ms sample
            
            with open("/sys/class/powercap/intel-rapl:0/energy_uj", "r") as f:
                energy2 = int(f.read().strip())
            
            delta_energy_j = (energy2 - energy1) / 1_000_000
            power_watts = delta_energy_j / 0.01
            return power_watts
        except:
            return None
    
    def _monitor_system_metrics(self):
        """Background thread to collect system metrics every 1ms"""
        print("Starting 1ms system metrics collection...")
        
        sample_count = 0
        start_time = time.perf_counter()
        
        while self.monitoring:
            try:
                # Get current timestamp
                timestamp = datetime.now()
                timestamp_formatted = timestamp.strftime("%H:%M:%S.%f")[:-3]
                
                # Get system metrics
                metrics = self._get_system_metrics()
                
                # Get currently executing function
                current_function = self._get_current_executing_function()
                
                # Determine function type
                if current_function is None:
                    function_type = 'idle'
                elif self._is_main_function(current_function):
                    function_type = 'main'
                else:
                    function_type = 'other'
                
                # Create metrics sample
                sample = SystemMetricsSample(
                    timestamp=timestamp,
                    timestamp_formatted=timestamp_formatted,
                    cpu_usage=metrics['cpu_usage'],
                    memory_usage=metrics['memory_usage'],
                    total_memory=metrics['total_memory'],
                    swap_usage=metrics['swap_usage'],
                    total_swap=metrics['total_swap'],
                    per_core_usage=metrics['per_core_usage'],
                    per_core_freq=metrics['per_core_freq'],
                    cpu_temperature=metrics['cpu_temperature'],
                    cpu_power=metrics['cpu_power'],
                    current_function=current_function,
                    function_type=function_type
                )
                
                # Store sample in appropriate categories
                self.metrics_samples.append(sample)
                self.whole_system_metrics.append(sample)
                
                if function_type == 'main':
                    self.main_function_metrics.append(sample)
                    # Also add to specific function's attributed metrics
                    if current_function:
                        self.function_stats[current_function]['attributed_metrics'].append(sample)
                elif function_type == 'other':
                    self.other_function_metrics.append(sample)
                
                sample_count += 1
                
                # Print progress every 1000 samples (1 second)
                if sample_count % 1000 == 0:
                    elapsed = time.perf_counter() - start_time
                    actual_frequency = sample_count / elapsed
                    print(f"Collected {sample_count} samples, actual frequency: {actual_frequency:.1f} Hz")
                
                # Sleep for remaining time to achieve 1ms intervals
                time.sleep(max(0, self.metrics_interval - 0.0001))  # Small buffer for processing time
                
            except Exception as e:
                print(f"Error in metrics collection: {e}")
                time.sleep(self.metrics_interval)
    
    def _save_metrics_to_csv(self):
        """Save all metrics samples to CSV file"""
        if not self.metrics_samples or not self._csv_file:
            return
        
        print(f"Saving {len(self.metrics_samples)} metrics samples to CSV...")
        
        try:
            with open(self._csv_file, 'w', newline='') as f:
                # Determine all possible fieldnames
                fieldnames = ['timestamp', 'timestamp_formatted', 'cpu_usage', 'memory_usage', 
                             'total_memory', 'swap_usage', 'total_swap', 'cpu_temperature', 
                             'cpu_power', 'current_function', 'function_type']
                
                # Add per-core fields if they exist
                if self.metrics_samples:
                    sample = self.metrics_samples[0]
                    fieldnames.extend(sample.per_core_usage.keys())
                    fieldnames.extend(sample.per_core_freq.keys())
                
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for sample in self.metrics_samples:
                    row = {
                        'timestamp': sample.timestamp.isoformat(),
                        'timestamp_formatted': sample.timestamp_formatted,
                        'cpu_usage': sample.cpu_usage,
                        'memory_usage': sample.memory_usage,
                        'total_memory': sample.total_memory,
                        'swap_usage': sample.swap_usage,
                        'total_swap': sample.total_swap,
                        'cpu_temperature': sample.cpu_temperature,
                        'cpu_power': sample.cpu_power,
                        'current_function': sample.current_function,
                        'function_type': sample.function_type
                    }
                    row.update(sample.per_core_usage)
                    row.update(sample.per_core_freq)
                    writer.writerow(row)
            
            print(f"Metrics saved to: {self._csv_file}")
        except Exception as e:
            print(f"Error saving CSV: {e}")
    
    def print_comprehensive_report(self):
        """Print comprehensive profiling report"""
        print("\n" + "="*100)
        print("COMPREHENSIVE INTEGRATED PROFILING REPORT")
        print("="*100)
        
        # Overall statistics
        total_samples = len(self.metrics_samples)
        main_samples = len(self.main_function_metrics)
        other_samples = len(self.other_function_metrics)
        idle_samples = total_samples - main_samples - other_samples
        
        print(f"\nOVERALL STATISTICS:")
        print(f"Total metrics samples collected: {total_samples}")
        print(f"Main function samples: {main_samples} ({main_samples/total_samples*100:.1f}%)")
        print(f"Other function samples: {other_samples} ({other_samples/total_samples*100:.1f}%)")
        print(f"Idle samples: {idle_samples} ({idle_samples/total_samples*100:.1f}%)")
        
        if total_samples > 0:
            duration_ms = total_samples * self.metrics_interval * 1000
            print(f"Total monitoring duration: {duration_ms:.1f} ms")
        
        # System resource breakdown
        print(f"\nSYSTEM RESOURCE BREAKDOWN:")
        print("-" * 80)
        
        categories = [
            ("MAIN FUNCTIONS", self.main_function_metrics),
            ("OTHER FUNCTIONS", self.other_function_metrics),
            ("WHOLE SYSTEM", self.whole_system_metrics)
        ]
        
        for category_name, samples in categories:
            if samples:
                avg_cpu = sum(s.cpu_usage for s in samples) / len(samples)
                max_cpu = max(s.cpu_usage for s in samples)
                avg_memory = sum(s.memory_usage for s in samples) / len(samples)
                max_memory = max(s.memory_usage for s in samples)
                
                power_samples = [s.cpu_power for s in samples if s.cpu_power is not None]
                avg_power = sum(power_samples) / len(power_samples) if power_samples else 0
                
                print(f"\n{category_name}:")
                print(f"  Samples: {len(samples)}")
                print(f"  CPU Usage: {avg_cpu:.1f}% avg, {max_cpu:.1f}% peak")
                print(f"  Memory Usage: {avg_memory:.1f}% avg, {max_memory:.1f}% peak")
                if avg_power > 0:
                    print(f"  CPU Power: {avg_power:.1f}W avg")
        
        # Individual function analysis
        print(f"\nINDIVIDUAL FUNCTION ANALYSIS:")
        print("-" * 80)
        
        # Filter significant functions
        significant_functions = {
            name: stats for name, stats in self.function_stats.items()
            if stats['total_time'] > 0.001 and stats['attributed_metrics']
        }
        
        sorted_functions = sorted(
            significant_functions.items(), 
            key=lambda x: len(x[1]['attributed_metrics']), 
            reverse=True
        )
        
        for func_name, stats in sorted_functions:
            samples = stats['attributed_metrics']
            
            print(f"\nFunction: {func_name}")
            print(f"  Calls: {stats['calls']}")
            print(f"  Total Time: {stats['total_time']:.6f} seconds")
            print(f"  Metrics Samples: {len(samples)}")
            
            if samples:
                avg_cpu = sum(s.cpu_usage for s in samples) / len(samples)
                max_cpu = max(s.cpu_usage for s in samples)
                avg_memory = sum(s.memory_usage for s in samples) / len(samples)
                max_memory = max(s.memory_usage for s in samples)
                
                print(f"  CPU Usage: {avg_cpu:.1f}% avg, {max_cpu:.1f}% peak")
                print(f"  Memory Usage: {avg_memory:.1f}% avg, {max_memory:.1f}% peak")
                
                power_samples = [s.cpu_power for s in samples if s.cpu_power is not None]
                if power_samples:
                    avg_power = sum(power_samples) / len(power_samples)
                    print(f"  CPU Power: {avg_power:.1f}W avg")
    
    def print_timeline_summary(self, max_samples=50):
        """Print timeline summary (limited samples for readability)"""
        print(f"\nTIMELINE SUMMARY (showing first {max_samples} samples):")
        print("-" * 80)
        
        print(f"{'Timestamp':<15} {'CPU%':<6} {'MEM%':<6} {'Function':<30} {'Type':<8}")
        print("-" * 80)
        
        samples_to_show = self.metrics_samples[:max_samples]
        for sample in samples_to_show:
            func_display = sample.current_function or "idle"
            if len(func_display) > 28:
                func_display = func_display[:25] + "..."
            
            print(f"{sample.timestamp_formatted:<15} "
                  f"{sample.cpu_usage:<6.1f} "
                  f"{sample.memory_usage:<6.1f} "
                  f"{func_display:<30} "
                  f"{sample.function_type:<8}")
        
        if len(self.metrics_samples) > max_samples:
            print(f"... and {len(self.metrics_samples) - max_samples} more samples")

# Create global profiler instance
profiler = IntegratedProfiler()

# Example functions to profile
def slow_function():
    """A CPU-intensive function"""
    total = 0
    for i in range(1000000):
        total += i
    return total

def fast_function():
    """A fast function using built-in sum"""
    return sum(range(1000000))

def memory_intensive_function():
    """A memory-intensive function"""
    large_list = [i**2 for i in range(100000)]
    return sum(large_list)

def io_function():
    """A function that does some I/O"""
    time.sleep(0.05)  # Simulate I/O wait
    return "IO completed"

def main():
    """Main function that calls other functions"""
    print("Starting main function...")
    
    result1 = slow_function()
    print(f"Slow function result: {result1}")
    
    result2 = fast_function()
    print(f"Fast function result: {result2}")
    
    result3 = memory_intensive_function()
    print(f"Memory intensive result: {result3}")
    
    result4 = io_function()
    print(f"IO function result: {result4}")
    
    print("Main function completed")

if __name__ == "__main__":
    # Add custom main function patterns if needed
    profiler.add_main_function_pattern('io_function')
    
    # Start monitoring
    profiler.start_monitoring()
    
    try:
        # Run main function
        main()
        
        # Let it run a bit longer to capture more metrics
        time.sleep(0.1)
        
    finally:
        # Stop monitoring and generate reports
        profiler.stop_monitoring()
        profiler.print_comprehensive_report()
        profiler.print_timeline_summary()
        
        print(f"\nDetailed metrics saved to: {profiler._csv_file}")
        print("Analysis complete!")