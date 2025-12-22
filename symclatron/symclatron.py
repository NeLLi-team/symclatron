#!/usr/bin/env python

# Standard library imports
import glob
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
from contextlib import contextmanager, nullcontext
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Union, Any, Tuple

# Third-party imports
import joblib
import numpy as np
import pandas as pd
import psutil
import pyhmmer
import shap
import typer
import xgboost as xgb

# Force TensorFlow to use CPU only
import os
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Suppress TensorFlow info/warning messages

from tensorflow.keras.models import load_model

# Define the script directory as a global variable for consistent path resolution
script_dir = os.path.dirname(os.path.abspath(__file__))

"""
symclatron: symbiont classifier
Author: Juan C. Villada
Email: jvillada@lbl.gov

US Department of Energy Joint Genome Institute (JGI)
Lawrence Berkeley National Laboratory (LBNL)
2025
"""

__version__ = "0.7.0"

def version_callback(value: bool):
    """Print version information."""
    if value:
        typer.echo(f"symclatron version {__version__}")
        raise typer.Exit()

def _build_shap_explainer(model: Any, data: pd.DataFrame) -> shap.Explainer:
    """Return a SHAP explainer compatible with XGBoost models across versions."""
    try:
        return shap.TreeExplainer(model)
    except Exception:
        return shap.Explainer(model.predict, data)


class ResourceMonitor:
    """
    Resource monitoring using psutil for comprehensive system metrics.

    This class provides real-time monitoring of CPU, memory, and execution time
    for both subprocess commands and Python tasks, without relying on external tools.
    """

    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = log_dir or os.path.join(os.getcwd(), "logs")
        os.makedirs(self.log_dir, exist_ok=True)

        # Create timestamped log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self.log_dir, f"resource_usage_{timestamp}.log")

        # Get the current process for monitoring
        self.process = psutil.Process()

        # Initialize tracking variables
        self.session_start_time = time.time()
        self.peak_memory_mb = 0.0
        self.peak_cpu_percent = 0.0
        self.total_tasks = 0
        self.subprocess_tasks = 0
        self.python_tasks = 0
        self.total_subprocess_time = 0.0
        self.total_python_time = 0.0

        # For background monitoring
        self._monitoring = False
        self._monitor_thread = None

        # Initialize log file
        self._init_log_file()

        # Start background monitoring
        self._start_background_monitoring()

    def _init_log_file(self):
        """Initialize log file with system information and header."""
        system_info = self._get_system_info()

        with open(self.log_file, 'w') as f:
            f.write("# symclatron Resource Usage Log\n")
            f.write(f"# Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("# System Information:\n")
            f.write(f"#   Python: {system_info['python_version']}\n")
            f.write(f"#   Platform: {system_info['platform']}\n")
            f.write(f"#   CPU Count: {system_info['cpu_count']}\n")
            f.write(f"#   Total Memory: {system_info['total_memory_gb']:.2f} GB\n")
            f.write(f"#   Available Memory: {system_info['available_memory_gb']:.2f} GB\n")
            f.write("=" * 80 + "\n\n")

    def _get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive system information."""
        memory = psutil.virtual_memory()

        return {
            'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            'platform': f"{platform.system()} {platform.release()}",
            'cpu_count': psutil.cpu_count(),
            'total_memory_gb': memory.total / (1024**3),
            'available_memory_gb': memory.available / (1024**3)
        }

    def _start_background_monitoring(self):
        """Start background thread to monitor peak resource usage."""
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._background_monitor, daemon=True)
        self._monitor_thread.start()

    def _background_monitor(self):
        """Background monitoring thread for tracking peak resource usage."""
        while self._monitoring:
            try:
                # Monitor memory usage
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / (1024**2)  # RSS in MB
                self.peak_memory_mb = max(self.peak_memory_mb, memory_mb)

                # Monitor CPU usage (averaged over 0.1 seconds)
                cpu_percent = self.process.cpu_percent()
                self.peak_cpu_percent = max(self.peak_cpu_percent, cpu_percent)

                time.sleep(0.1)  # Sample every 100ms
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            except Exception:
                # Continue monitoring even if there are transient errors
                pass

    def _stop_background_monitoring(self):
        """Stop background monitoring thread."""
        self._monitoring = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)

    @contextmanager
    def monitor_task(self, task_name: str, task_type: str = "python"):
        """
        Context manager for monitoring a task's resource usage.

        Args:
            task_name: Descriptive name for the task
            task_type: Either "python" or "subprocess"
        """
        # Record initial state
        start_time = time.time()
        start_memory = self.process.memory_info().rss / (1024**2)  # MB
        start_cpu_time = sum(self.process.cpu_times()[:2])  # user + system

        try:
            yield

        finally:
            # Calculate resource usage
            end_time = time.time()
            end_memory = self.process.memory_info().rss / (1024**2)  # MB
            end_cpu_time = sum(self.process.cpu_times()[:2])  # user + system

            duration = end_time - start_time
            memory_delta = end_memory - start_memory
            cpu_time_used = end_cpu_time - start_cpu_time

            # Update counters
            self.total_tasks += 1
            if task_type == "subprocess":
                self.subprocess_tasks += 1
                self.total_subprocess_time += duration
            else:
                self.python_tasks += 1
                self.total_python_time += duration

            # Log the task
            self._log_task(task_name, task_type, duration, memory_delta, cpu_time_used)

    def _log_task(self, task_name: str, task_type: str, duration: float,
                  memory_delta: float, cpu_time: float):
        """Log individual task performance."""
        timestamp = datetime.now().strftime('%H:%M:%S')

        with open(self.log_file, 'a') as f:
            f.write(f"{timestamp} | {task_name:<35} | {task_type:<10} | "
                   f"{duration:>8.2f}s | {memory_delta:>+8.1f}MB | {cpu_time:>6.2f}s CPU\n")

    def run_subprocess_with_monitoring(self, cmd: List[str], description: str) -> subprocess.CompletedProcess:
        """
        Run a subprocess command with comprehensive monitoring.

        Args:
            cmd: Command list to execute
            description: Description for logging

        Returns:
            subprocess.CompletedProcess result
        """
        with self.monitor_task(description, "subprocess"):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)

                # Log command details
                cmd_str = ' '.join(cmd)
                status = "SUCCESS" if result.returncode == 0 else f"FAILED({result.returncode})"

                with open(self.log_file, 'a') as f:
                    f.write(f"    Command: {cmd_str}\n")
                    f.write(f"    Status: {status}\n")
                    if result.returncode != 0 and result.stderr:
                        f.write(f"    Error: {result.stderr.strip()[:200]}...\n")
                    f.write("-" * 80 + "\n")

                return result

            except Exception as e:
                with open(self.log_file, 'a') as f:
                    f.write(f"    Exception: {str(e)}\n")
                    f.write("-" * 80 + "\n")
                raise

    def log_python_task(self, task_name: str, duration: float,
                       memory_used: Optional[float] = None,
                       additional_info: Optional[str] = None):
        """
        Log a Python task that was executed outside the context manager.

        Args:
            task_name: Name of the task
            duration: Duration in seconds
            memory_used: Optional memory usage in MB
            additional_info: Optional additional information
        """
        self.python_tasks += 1
        self.total_python_time += duration
        self.total_tasks += 1

        timestamp = datetime.now().strftime('%H:%M:%S')
        memory_str = f"{memory_used:>+8.1f}MB" if memory_used else "   N/A  MB"

        with open(self.log_file, 'a') as f:
            f.write(f"{timestamp} | {task_name:<35} | python     | "
                   f"{duration:>8.2f}s | {memory_str} | external\n")
            if additional_info:
                f.write(f"    Info: {additional_info}\n")
            f.write("-" * 80 + "\n")

    def finalize(self, total_execution_time_mins: float):
        """Generate comprehensive final resource usage report."""
        self._stop_background_monitoring()

        # Calculate final statistics
        session_duration_mins = (time.time() - self.session_start_time) / 60
        peak_memory_gb = self.peak_memory_mb / 1024
        efficiency = (self.total_python_time + self.total_subprocess_time) / (session_duration_mins * 60) * 100

        # Generate detailed report
        report_data = {
            'execution_time_mins': total_execution_time_mins,
            'session_duration_mins': session_duration_mins,
            'total_tasks': self.total_tasks,
            'subprocess_tasks': self.subprocess_tasks,
            'python_tasks': self.python_tasks,
            'subprocess_time': self.total_subprocess_time,
            'python_time': self.total_python_time,
            'peak_memory_gb': peak_memory_gb,
            'peak_cpu_percent': self.peak_cpu_percent,
            'efficiency_percent': efficiency
        }

        self._write_final_report(report_data)
        self._print_console_summary(report_data)

    def _write_final_report(self, data: Dict[str, float]):
        """Write detailed final report to log file."""
        with open(self.log_file, 'a') as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write("FINAL RESOURCE USAGE SUMMARY\n")
            f.write("=" * 80 + "\n")
            f.write(f"Session Duration: {data['session_duration_mins']:.1f} minutes\n")
            f.write(f"Reported Execution Time: {data['execution_time_mins']:.1f} minutes\n")
            f.write(f"\nTask Statistics:\n")
            f.write(f"  Total tasks executed: {data['total_tasks']}\n")
            f.write(f"  Subprocess tasks: {data['subprocess_tasks']}\n")
            f.write(f"  Python tasks: {data['python_tasks']}\n")
            f.write(f"\nTime Breakdown:\n")
            f.write(f"  Subprocess time: {data['subprocess_time']:.2f} seconds\n")
            f.write(f"  Python task time: {data['python_time']:.2f} seconds\n")
            f.write(f"  Total active time: {data['subprocess_time'] + data['python_time']:.2f} seconds\n")
            f.write(f"\nResource Usage:\n")
            f.write(f"  Peak memory usage: {data['peak_memory_gb']:.3f} GB\n")
            f.write(f"  Peak CPU usage: {data['peak_cpu_percent']:.1f}%\n")
            f.write(f"  CPU efficiency: {data['efficiency_percent']:.1f}%\n")
            f.write(f"\nSession ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    def _print_console_summary(self, data: Dict[str, float]):
        """Print summary to console."""
        summary = f"""
✅ Resource monitoring completed!
   Total tasks executed: {data['total_tasks']} (subprocess: {data['subprocess_tasks']}, python: {data['python_tasks']})
   Peak memory usage: {data['peak_memory_gb']:.3f} GB
   Peak CPU usage: {data['peak_cpu_percent']:.1f}%
   Execution time: {data['execution_time_mins']:.1f} minutes
   CPU efficiency: {data['efficiency_percent']:.1f}%
"""
        typer.secho(summary, fg=typer.colors.CYAN)

    def __del__(self):
        """Cleanup when object is destroyed."""
        self._stop_background_monitoring()


def print_header():
    """Print symclatron header with version."""
    header = f"""
symclatron v{__version__} - symbiont classifier

Machine learning-based classification of microbial symbiotic lifestyles

Author: Juan C. Villada <jvillada@lbl.gov>
US DOE Joint Genome Institute (JGI)
Lawrence Berkeley National Laboratory (LBNL)
"""
    typer.secho(header, fg=typer.colors.CYAN, bold=True)


def greetings():
    """Legacy function for compatibility."""
    print_header()


def init_message_setup() -> None:
    """Print a setup message to the console."""
    message = "\n" + "-" * 10 + " Setup data workflow " + "-" * 10 + "\n"
    message = typer.style(text=message, fg=typer.colors.BRIGHT_GREEN, bold=False)
    return typer.echo(message)


def init_message_build() -> None:
    """Print a build message to the console."""
    message = "Building classifiers workflow\n"
    message = typer.style(text=message, fg=typer.colors.BRIGHT_GREEN, bold=False)
    return typer.echo(message)


def init_message_classify() -> None:
    """Print a classification message to the console."""
    message = "\n" + "-" * 10 + " Classifying genomes workflow " + "-" * 10 + "\n"
    message = typer.style(text=message, fg=typer.colors.BRIGHT_GREEN, bold=False)
    return typer.echo(message)


def extract_data() -> None:
    """Download and extract the symclatron data archive."""
    typer.secho("Setting up symclatron data", fg=typer.colors.BRIGHT_GREEN)

    # URL for the data archive
    data_url = "https://portal.nersc.gov/cfs/nelli/symclatron_db.tar.gz"

    # Check if data directory already exists
    if os.path.isdir(os.path.join(script_dir, "data")):
        typer.secho("Data directory already exists. Using existing data.", fg=typer.colors.BRIGHT_YELLOW)
        return

    # Create a temporary file path
    tmp_download_path = os.path.join(script_dir, "symclatron_db.tar.gz")

    try:
        # Download the file
        typer.secho(f"Downloading data from {data_url}...", fg=typer.colors.BRIGHT_GREEN)
        urllib.request.urlretrieve(data_url, tmp_download_path)

        # Extract the archive
        typer.secho("Extracting data...", fg=typer.colors.BRIGHT_GREEN)
        data_tar = tarfile.open(tmp_download_path)
        data_tar.extractall(script_dir)
        data_tar.close()

        # Move the data directory to the correct location
        if os.path.isdir(os.path.join(script_dir, "symclatron_db", "data")):
            # If the data is inside a subdirectory, move it up
            if not os.path.isdir(os.path.join(script_dir, "data")):
                shutil.move(os.path.join(script_dir, "symclatron_db", "data"), script_dir)

            # Clean up the symclatron_db directory if it exists
            if os.path.isdir(os.path.join(script_dir, "symclatron_db")):
                shutil.rmtree(os.path.join(script_dir, "symclatron_db"))

        # Remove the downloaded archive
        if os.path.exists(tmp_download_path):
            os.remove(tmp_download_path)

        typer.secho("[OK] Data setup complete\n", fg=typer.colors.BRIGHT_MAGENTA)

    except Exception as e:
        typer.secho(
            f"[Error] Failed to download or extract data: {str(e)}",
            fg=typer.colors.BRIGHT_RED,
            err=True,
        )
        # If the download fails, let the user know they can manually download and extract
        typer.secho(
            f"\nPlease download the data manually from {data_url} and extract it to {os.path.join(script_dir, 'data')}",
            fg=typer.colors.BRIGHT_YELLOW,
        )
        exit(1)



def create_output_dir(logger: logging.Logger) -> None:
    """
    Create the output directory for results.

    Parameters:
    logger (logging.Logger): Logger object for logging messages
    """
    logger.info("Creating output directory")
    if os.path.exists(savedir):
        logger.error(f"Output directory '{savedir}' already exists")
        typer.secho(
            "[Error] Output directory already exists",
            fg=typer.colors.BRIGHT_RED,
            err=True,
        )
        exit(1)
    else:
        os.mkdir(savedir)
        logger.info(f"Output directory created at: {savedir}")
        typer.secho(
            f"[OK] Output directory created at: {savedir} \n",
            fg=typer.colors.BRIGHT_MAGENTA,
        )


def create_tmp_dir(logger: logging.Logger) -> None:
    """
    Create temporary directory for intermediate files.

    Parameters:
    logger (logging.Logger): Logger object for logging messages
    """
    logger.info(f"Creating temporary directory: {tmp_dir_path}")
    if os.path.exists(tmp_dir_path):
        logger.error(f"Temporary directory '{tmp_dir_path}' already exists")
        typer.secho(
            "[Error] Output tmp directory already exists",
            fg=typer.colors.BRIGHT_RED,
            err=True,
        )
        exit(1)
    else:
        os.mkdir(tmp_dir_path)
        logger.debug(f"Temporary directory created successfully")


def copy_genomes_to_tmp_dir() -> str:
    """Copy genomes to a temporary directory.

    Returns:
        str: Path to the temporary directory containing the genomes.
    """
    tmp_genome_dir_path = f"{tmp_dir_path}/renamed_genomes"
    os.mkdir(tmp_genome_dir_path)
    for each_file in glob.glob(genomedir + "/*.faa"):
        shutil.copy(each_file, tmp_genome_dir_path)
    return tmp_genome_dir_path


def rename_genomes(tmp_genome_dir_path: str) -> str:
    """Rename genomes to a simplified format.

    Args:
        tmp_genome_dir_path (str): Path to the temporary directory containing the genomes.

    Returns:
        str: Path to the JSON file containing the mapping of new to original genome names.
    """
    genome_file_paths = glob.glob(tmp_genome_dir_path + "/*.faa")
    genome_names = [x.split("/")[-1].split(".faa")[0] for x in genome_file_paths]
    # the dictionary will have as keys the new simplified name of the genome and as values the original name
    # the simplied name will be genome_1, genome_2, etc
    genome_dict = {f"genome_{i+1}": genome_names[i] for i in range(len(genome_names))}

    genome_dict_path = f"{tmp_dir_path}/genomes_dict.json"
    with open(genome_dict_path, "w") as outfile:
        json.dump(genome_dict, outfile)

    # rename the faa fasta files with the new simplified names using the genome_dict
    for each_genome in genome_file_paths:
        genome_name = each_genome.split("/")[-1].split(".faa")[0]
        new_name = f"{tmp_genome_dir_path}/{list(genome_dict.keys())[list(genome_dict.values()).index(genome_name)]}.faa"
        os.rename(each_genome, new_name)

    typer.secho("[OK] Genomes renamed\n", fg=typer.colors.BRIGHT_MAGENTA)

    return genome_dict_path


def rename_all_proteins_in_fasta_files(tmp_genome_dir_path: str, savedir: str) -> None:
    """Rename all proteins in FASTA files to a simplified format.

    Args:
        tmp_genome_dir_path (str): Path to the temporary directory containing the genomes.
        savedir (str): Path to the output directory.
    """
    genome_file_paths = glob.glob(tmp_genome_dir_path + "/*.faa")
    for each_genome in genome_file_paths:
        # create a json dictionary with the original protein names and the new simplified names
        # the simplified names will be protein_1, protein_2, etc
        with open(each_genome, "r") as infile:
            proteins = [line for line in infile if line.startswith(">")]
            proteins = [x.split()[0].replace(">", "") for x in proteins]
            proteins_dict = {
                f"protein_{i+1}": proteins[i] for i in range(len(proteins))
            }
        with open(f"{each_genome.split('.faa')[0]}_dict.json", "w") as outfile:
            json.dump(proteins_dict, outfile)

        # rename the proteins in the fasta file
        with open(each_genome, "r") as infile:
            genome_name = each_genome.split("/")[-1].replace(".faa", "")
            with open(f"{each_genome.replace(".faa", "_renamed.faa")}", "w") as outfile:
                for line in infile:
                    if line.startswith(">"):
                        new_name = f">{genome_name}|protein_{proteins.index(line.split()[0].replace(">", ""))+1}\n"
                        outfile.write(new_name)
                    else:
                        outfile.write(line)
        # delete the original fasta file
        os.remove(each_genome)

        # rename the new fasta file with the original name
        os.rename(f"{each_genome.replace('.faa', '_renamed.faa')}", each_genome)

    typer.secho("[OK] Proteins renamed\n", fg=typer.colors.BRIGHT_MAGENTA)



def merge_genomes(tmp_genomes_path: str) -> None:
    """Merge all genomes into a single FASTA file.

    Args:
        tmp_genomes_path (str): Path to the temporary directory containing the genomes.
    """
    typer.secho("Merging genomes", fg=typer.colors.BRIGHT_GREEN)
    genome_file_paths = glob.glob(f"{tmp_genomes_path}/*.faa")
    output_file = f"{tmp_dir_path}/merged_genomes.faa"
    with open(output_file, "w") as outfile:
        for each_file in genome_file_paths:
            with open(each_file) as infile:
                for line in infile:
                    outfile.write(line)
    typer.secho(
        f"[OK] Fasta files merged at: {output_file} \n", fg=typer.colors.BRIGHT_MAGENTA
    )



def run_hmmsearch(ncpus: int, resource_monitor: Optional["ResourceMonitor"] = None) -> None:
    """Run hmmsearch on the merged genomes using pyhmmer.

    Args:
        ncpus (int): Number of CPUs to use.
        resource_monitor (ResourceMonitor, optional): Resource monitor object. Defaults to None.
    """
    typer.secho(
        "Running hmmsearch on merged genomes for the hmm models file:\n",
        fg=typer.colors.BRIGHT_GREEN,
    )

    path_to_tblout = (
        Path(tmp_dir_path) / "symclatron_2384_union_features_hmmsearch.tblout"
    )

    # Load HMM file using pyhmmer
    hmm_file_path = os.path.join(script_dir, "data/symclatron_2384_union_features.hmm")
    sequence_file_path = f"{tmp_dir_path}/merged_genomes.faa"

    try:
        # Use resource monitoring context manager for the entire HMMER search
        if resource_monitor:
            monitor_context = resource_monitor.monitor_task("HMMER search (symclatron features)", "python")
        else:
            monitor_context = nullcontext()

        with monitor_context:
            # Load HMM profiles
            with pyhmmer.plan7.HMMFile(hmm_file_path) as hmm_file:
                hmms = list(hmm_file)

            # Load sequences
            with pyhmmer.easel.SequenceFile(sequence_file_path, digital=True) as seq_file:
                sequences = list(seq_file)

            # Run hmmsearch
            all_hits = []
            for hits in pyhmmer.hmmsearch(hmms, sequences, cpus=ncpus, E=1000, incE=1000):
                query_name = hits.query.name.decode()
                for hit in hits:
                    for domain in hit.domains:
                        # Format similar to HMMER tblout format
                        all_hits.append({
                            'target_name': hit.name.decode(),
                            'accession': '-',
                            'query_name': query_name,
                            'accession_q': '-',
                            'full_evalue': hit.evalue,
                            'full_score': hit.score,
                            'full_bias': hit.bias,
                            'domain_evalue': domain.i_evalue,  # Use i_evalue (independent evalue)
                            'domain_score': domain.score,
                            'domain_bias': domain.bias,
                            'hmm_from': domain.alignment.hmm_from,
                            'hmm_to': domain.alignment.hmm_to,
                            'ali_from': domain.alignment.target_from,
                            'ali_to': domain.alignment.target_to,
                            'env_from': domain.env_from,  # Use domain env_from
                            'env_to': domain.env_to,      # Use domain env_to
                            'acc': 0.0  # pyhmmer doesn't have domain accuracy, set to 0
                        })

            # Write results in HMMER tblout format
            with open(path_to_tblout, 'w') as f:
                # Write header comments
                f.write("# hmmsearch :: search sequence(s) against a profile database\n")
                f.write("# target name        accession   query name           accession   E-value  score  bias   ")
                f.write("E-value  score  bias   from    to  from    to  from    to   acc\n")
                f.write("#        description   --------- ----------- --------- ------ ----- ----- ")
                f.write(" ------ ----- -----   ---- ---- ---- ---- ---- ----   ----\n")

                for hit in all_hits:
                    line = f"{hit['target_name']:<20} {hit['accession']:<9} {hit['query_name']:<19} " \
                           f"{hit['accession_q']:<9} {hit['full_evalue']:8.1e} {hit['full_score']:6.1f} " \
                           f"{hit['full_bias']:5.1f} {hit['domain_evalue']:8.1e} {hit['domain_score']:6.1f} " \
                           f"{hit['domain_bias']:5.1f} {hit['hmm_from']:4d} {hit['hmm_to']:4d} " \
                           f"{hit['ali_from']:4d} {hit['ali_to']:4d} {hit['env_from']:4d} " \
                           f"{hit['env_to']:4d} {hit['acc']:6.3f}\n"
                    f.write(line)

        typer.secho(
            f"[OK] Hmmsearch output saved at: {path_to_tblout} \n",
            fg=typer.colors.BRIGHT_MAGENTA,
        )

    except Exception as e:
        typer.secho(f"Error in pyhmmer search: {str(e)}", fg=typer.colors.RED, err=True)
        raise



def run_hmmsearch_uni56(ncpus: int, resource_monitor: Optional["ResourceMonitor"] = None) -> None:
    """Run hmmsearch for UNI56 markers using pyhmmer.

    Args:
        ncpus (int): Number of CPUs to use.
        resource_monitor (ResourceMonitor, optional): Resource monitor object. Defaults to None.
    """
    hmmfile = os.path.join(script_dir, "data/uni56.hmm")
    uni56_tblout = Path(tmp_dir_path) / "uni56_hmmsearch.tblout"
    sequence_file_path = tmp_dir_path + "/merged_genomes.faa"

    try:
        # Use resource monitoring context manager for the entire UNI56 HMMER search
        if resource_monitor:
            monitor_context = resource_monitor.monitor_task("HMMER search (UNI56 markers)", "python")
        else:
            monitor_context = nullcontext()

        with monitor_context:
            # Load HMM profiles
            with pyhmmer.plan7.HMMFile(hmmfile) as hmm_file:
                hmms = list(hmm_file)

            # Load sequences
            with pyhmmer.easel.SequenceFile(sequence_file_path, digital=True) as seq_file:
                sequences = list(seq_file)

            # Run hmmsearch with gathering thresholds (cut_ga equivalent)
            all_hits = []
            for hits in pyhmmer.hmmsearch(hmms, sequences, cpus=ncpus, bit_cutoffs="gathering"):
                query_name = hits.query.name.decode()
                for hit in hits:
                    for domain in hit.domains:
                        # Format similar to HMMER tblout format
                        all_hits.append({
                            'target_name': hit.name.decode(),
                            'accession': '-',
                            'query_name': query_name,
                            'accession_q': '-',
                            'full_evalue': hit.evalue,
                            'full_score': hit.score,
                            'full_bias': hit.bias,
                            'domain_evalue': domain.i_evalue,  # Use i_evalue (independent evalue)
                            'domain_score': domain.score,
                            'domain_bias': domain.bias,
                            'hmm_from': domain.alignment.hmm_from,
                            'hmm_to': domain.alignment.hmm_to,
                            'ali_from': domain.alignment.target_from,
                            'ali_to': domain.alignment.target_to,
                            'env_from': domain.env_from,  # Use domain env_from
                            'env_to': domain.env_to,      # Use domain env_to
                            'acc': 0.0  # pyhmmer doesn't have domain accuracy, set to 0
                        })

            # Write results in HMMER tblout format
            with open(uni56_tblout, 'w') as f:
                # Write header comments
                f.write("# hmmsearch :: search sequence(s) against a profile database\n")
                f.write("# target name        accession   query name           accession   E-value  score  bias   ")
                f.write("E-value  score  bias   from    to  from    to  from    to   acc\n")
                f.write("#        description   --------- ----------- --------- ------ ----- ----- ")
                f.write(" ------ ----- -----   ---- ---- ---- ---- ---- ----   ----\n")

                for hit in all_hits:
                    line = f"{hit['target_name']:<20} {hit['accession']:<9} {hit['query_name']:<19} " \
                           f"{hit['accession_q']:<9} {hit['full_evalue']:8.1e} {hit['full_score']:6.1f} " \
                           f"{hit['full_bias']:5.1f} {hit['domain_evalue']:8.1e} {hit['domain_score']:6.1f} " \
                           f"{hit['domain_bias']:5.1f} {hit['hmm_from']:4d} {hit['hmm_to']:4d} " \
                           f"{hit['ali_from']:4d} {hit['ali_to']:4d} {hit['env_from']:4d} " \
                           f"{hit['env_to']:4d} {hit['acc']:6.3f}\n"
                    f.write(line)

        typer.secho(
            f"[OK] Hmmsearch output saved at: {uni56_tblout} \n",
            fg=typer.colors.BRIGHT_MAGENTA,
        )

    except Exception as e:
        typer.secho(f"Error in UNI56 pyhmmer search: {str(e)}", fg=typer.colors.RED, err=True)
        raise



def save_list_of_models() -> None:
    """Save a list of models from HMM files using pyhmmer."""
    typer.secho(
        "Saving list of models for each hmm model file", fg=typer.colors.BRIGHT_GREEN
    )

    hmm_files = [
        os.path.join(script_dir, "data/symclatron_2384_union_features.hmm"),
        os.path.join(script_dir, "data/uni56.hmm")
    ]

    for hmmfile in hmm_files:
        models_list_file_path = (
            tmp_dir_path + "/" + os.path.basename(hmmfile).split(".")[0] + "_models.list"
        )

        try:
            with open(models_list_file_path, "w") as output_models_list_file:
                # Use pyhmmer to read HMM profiles and extract names
                with pyhmmer.plan7.HMMFile(hmmfile) as hmm_file:
                    for hmm in hmm_file:
                        # Write the model name (equivalent to "NAME" field)
                        output_models_list_file.write(hmm.name.decode() + "\n")
        except Exception as e:
            typer.secho(f"Error reading HMM file {hmmfile}: {str(e)}", fg=typer.colors.RED, err=True)
            # Fallback to the original text parsing method
            with open(models_list_file_path, "w") as output_models_list_file:
                with open(hmmfile, "r") as my_hmmfile:
                    for line in my_hmmfile:
                        if re.search("NAME", line):
                            output_models_list_file.write(line.replace("NAME  ", ""))

    typer.secho("[OK] Models list saved\n", fg=typer.colors.BRIGHT_MAGENTA)


def save_list_of_genomes(tmp_genomes_path: str) -> None:
    """Save a list of genomes to a file.

    Args:
        tmp_genomes_path (str): Path to the temporary directory containing the genomes.
    """
    typer.secho("Saving list of genomes", fg=typer.colors.BRIGHT_GREEN)

    list_of_genome_files = glob.glob(f"{tmp_genomes_path}/genome_*.faa")

    genomes_list_file_path = tmp_dir_path + "/genomes.list"

    with open(genomes_list_file_path, "w") as output_genomes_list_file:
        for each_element in list_of_genome_files:
            output_genomes_list_file.write(
                each_element.split("/")[-1].split(".faa")[0] + "\n"
            )

    typer.secho("[OK] Genomes list saved\n", fg=typer.colors.BRIGHT_MAGENTA)



def hmmer_results_to_pandas_df() -> None:
    """Convert HMMER results to a pandas DataFrame."""
    typer.secho(
        "Generating matrix of highest scores from the hmmsearch output",
        fg=typer.colors.BRIGHT_GREEN,
    )

    list_of_tblout_hmmsearch_output_files = glob.glob(
        tmp_dir_path + "/*_hmmsearch.tblout"
    )

    for tbloutfile in list_of_tblout_hmmsearch_output_files:
        tblout_hmm_result = pd.read_csv(
            tbloutfile, header=None, sep=r"\s+", comment="#", usecols=[0, 2, 4, 5]
        )

        # list_of_features_names = []
        models_names = pd.read_csv(
            tbloutfile.replace("_hmmsearch.tblout", "_models.list"),
            sep="\t",
            header=None,
        )

        genomes_names = pd.read_csv(
            tmp_dir_path + "/genomes.list", sep="\t", header=None
        )

        # Process hmmsearch output
        tblout_hmm_result = tblout_hmm_result.rename(
            columns={0: "taxon_oid", 2: "model", 4: "evalue", 5: "score"}
        )

        tblout_hmm_result["protein_name"] = tblout_hmm_result["taxon_oid"].str.replace(
            ".*\\|", "", regex=True
        )
        tblout_hmm_result["taxon_oid"] = tblout_hmm_result["taxon_oid"].str.replace(
            "\\|.*$", "", regex=True
        )

        # Grouping by COG and keeping only the max score
        tblout_hmm_result = (
            tblout_hmm_result.groupby(["taxon_oid", "model"]).max().reset_index()
        )

        df_hits_with_protein_names_loc = tbloutfile.replace(
            "_hmmsearch.tblout", "_hits_with_protein_names.tsv"
        )

        global symclatron_union_hits_with_protein_names_loc
        symclatron_union_hits_with_protein_names_loc = f"{os.path.dirname(tbloutfile)}/symclatron_2384_union_features_hits_with_protein_names.tsv"

        tblout_hmm_result.to_csv(
            df_hits_with_protein_names_loc,
            index=False,
            sep="\t",
        )

        tblout_hmm_result = tblout_hmm_result[["taxon_oid", "model", "score"]]
        tblout_hmm_result = tblout_hmm_result.sort_values(
            by=["taxon_oid", "model", "score"])
        tblout_hmm_result = tblout_hmm_result.drop_duplicates()
        tblout_hmm_result = tblout_hmm_result.pivot_table(
            index="taxon_oid", columns="model", values="score", fill_value=0
        )

        # Processing all taxa names
        genomes_names = genomes_names.rename(columns={0: "taxon_oid"})
        genomes_names = genomes_names.sort_values(by=["taxon_oid"])

        # Merge dataframes based on taxa names
        tblout_hmm_result = pd.merge(
            left=genomes_names, right=tblout_hmm_result, on="taxon_oid", how="left"
        )

        # Fill missing values for which hmmsearch did not find any result even with the large E-value thresholds
        # This missing values are normally due to sequences being of such low quality that they do not pass the hmmsearch filters
        tblout_hmm_result.fillna(float(0.0), inplace=True)

        # Load all model names to complete matrix with all COG models analysed
        models_names = models_names.rename(columns={0: "model"})
        missing_models = set(models_names["model"]) - set(
            tblout_hmm_result.drop(["taxon_oid"], axis=1).columns
        )
        if len(missing_models) > 0:
            for xmodel in missing_models:
                # tblout_hmm_result[xmodel] = float(0)
                new_column = pd.DataFrame(
                    float(0.0),
                    index=range(len(tblout_hmm_result.index)),
                    columns=[xmodel],
                )
                tblout_hmm_result = pd.concat([tblout_hmm_result, new_column], axis=1)

        # Sort columns alphabetically, except for taxon_oid column which should be the first one
        tblout_hmm_result = tblout_hmm_result.reindex(
            sorted(tblout_hmm_result.columns), axis=1
        )
        tblout_hmm_result = tblout_hmm_result[
            ["taxon_oid"]
            + [col for col in tblout_hmm_result.columns if col != "taxon_oid"]
        ]
        # Save output
        tblout_hmm_result.to_csv(
            tbloutfile.replace("_hmmsearch.tblout", "_hits_all_models.tsv"),
            index=False,
            sep="\t",
        )

    typer.secho(
        "[OK] All 'hits_all_models' tables saved\n", fg=typer.colors.BRIGHT_MAGENTA
    )



def split_hits_all_models_for_3_models() -> None:
    """Split the hits all models table into three separate tables for each model."""
    path_to_df = f"{tmp_dir_path}/symclatron_2384_union_features_hits_all_models.tsv"
    # Load the df
    df = pd.read_csv(path_to_df, sep="\t")

    # -------------------------------- df_1: symcla
    # get the list from the json file using relative path to script
    symcla_json_path = os.path.join(script_dir, "data/features_names_list_symcla.json")
    df_1_symcla_list_of_columns = json.load(open(symcla_json_path, "r"))

    df_1_symcla = df[["taxon_oid"] + df_1_symcla_list_of_columns]
    df_1_symcla.to_csv(
        tmp_dir_path + "/symcla_hits_all_models.tsv", sep="\t", index=False
    )

    # -------------------------------- df_2: symreg
    # get the list from the json file using relative path to script
    symreg_json_path = os.path.join(script_dir, "data/features_names_list_symreg.json")
    df_2_symreg_list_of_columns = json.load(open(symreg_json_path, "r"))

    df_2_symreg = df[["taxon_oid"] + df_2_symreg_list_of_columns]
    df_2_symreg.to_csv(
        tmp_dir_path + "/symreg_hits_all_models.tsv", sep="\t", index=False
    )

    # -------------------------------- df_3: hostcla
    # get the list from the json file using relative path to script
    hostcla_json_path = os.path.join(script_dir, "data/features_names_list_hostcla.json")
    df_3_hostcla_list_of_columns = json.load(open(hostcla_json_path, "r"))

    df_3_hostcla = df[["taxon_oid"] + df_3_hostcla_list_of_columns]
    df_3_hostcla.to_csv(
        tmp_dir_path + "/hostcla_hits_all_models.tsv", sep="\t", index=False
    )



def classify_genomes_internal(resource_monitor: Optional["ResourceMonitor"] = None) -> None:
    """Classify genomes using the three XGBoost models.

    Args:
        resource_monitor (ResourceMonitor, optional): Resource monitor object. Defaults to None.
    """
    for each_model in ["symcla", "symreg", "hostcla"]:
        start_time = time.time()
        typer.secho(
            f"Classifying genomes using the {each_model} model",
            fg=typer.colors.BRIGHT_GREEN,
        )

        all_tblout_df = pd.read_csv(
            f"{tmp_dir_path}/{each_model}_hits_all_models.tsv",
            sep="\t"
        )
        all_tblout_df.to_csv(
            f"{savedir}/bitscore_{each_model}.tsv", sep="\t", index=False
        )

        features_gt0 = all_tblout_df.drop(["taxon_oid"], axis=1).apply(
            lambda x: x[x > 0].count(), axis=1
        )
        features_ge20 = all_tblout_df.drop(["taxon_oid"], axis=1).apply(
            lambda x: x[x >= 20].count(), axis=1
        )
        features_ge100 = all_tblout_df.drop(["taxon_oid"], axis=1).apply(
            lambda x: x[x >= 100].count(), axis=1
        )
        tblout_hmm_result_total_models = pd.concat(
            [all_tblout_df["taxon_oid"], features_gt0, features_ge20, features_ge100],
            axis=1,
        )
        tblout_hmm_result_total_models.columns = [
            "taxon_oid",
            "features_gt0",
            "features_ge20",
            "features_ge100",
        ]
        tblout_hmm_result_total_models.to_csv(
            f"{tmp_dir_path}/total_models_per_genome_{each_model}.tsv",
            sep="\t",
            index=False,
        )

        taxon_oid_list = all_tblout_df["taxon_oid"].tolist()

        all_tblout_df.drop(["taxon_oid"], axis=1, inplace=True)

        if each_model == "symreg":
            xgb_model = xgb.XGBRegressor()
        else:
            xgb_model = xgb.XGBClassifier()

        # Use path relative to the script's location for loading models
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 f"data/ml_models/{each_model}.json")
        xgb_model.load_model(model_path)

        # Initialize predictions_df for all model types
        predictions_df = pd.DataFrame({"taxon_oid": taxon_oid_list})

        if each_model == "symreg":
            symreg_prediction = xgb_model.predict(all_tblout_df)
            predictions_df["symreg_score"] = symreg_prediction

            # SHAP calculation only for symreg model
            typer.secho("Computing SHAP values", fg=typer.colors.BRIGHT_GREEN)
            explainer = _build_shap_explainer(xgb_model, all_tblout_df)
            shap_values = explainer(all_tblout_df)

            # Save SHAP values for symreg
            shap_df = pd.DataFrame(shap_values.values, columns=all_tblout_df.columns)
            shap_df["taxon_oid"] = taxon_oid_list
            shap_df = shap_df[
                ["taxon_oid"] + [col for col in shap_df.columns if col != "taxon_oid"]
            ]
            shap_df.to_csv(f"{savedir}/shap_{each_model}.tsv", sep="\t", index=False)

        elif each_model == "symcla":
            class_labels = ["proba_fl", "proba_ha", "proba_in"]
            symcla_prediction = xgb_model.predict_proba(all_tblout_df)
            prob_df = pd.DataFrame(symcla_prediction, columns=class_labels)
            predictions_df = pd.concat([predictions_df, prob_df], axis=1)
            predictions_df["max_proba_symcla"] = predictions_df[class_labels].idxmax(axis="columns")

        elif each_model == "hostcla":
            class_labels = ["hostcla_proba_no", "hostcla_proba_yes"]
            hostcla_prediction = xgb_model.predict_proba(all_tblout_df)
            prob_df = pd.DataFrame(hostcla_prediction, columns=class_labels)
            predictions_df = pd.concat([predictions_df, prob_df], axis=1)
            predictions_df["max_proba_hostcla"] = predictions_df[class_labels].idxmax(axis="columns")

        predictions_df.to_csv(
            f"{tmp_dir_path}/{each_model}_predictions.tsv", sep="\t", index=False
        )

        end_time = time.time()
        duration = end_time - start_time

        if resource_monitor:
            # Log resource usage for each ML model
            resource_monitor.log_python_task(f"ML Classification ({each_model})", duration, None, f"Model: {each_model}")

        typer.secho(
            f"[OK] Genomes classified with {each_model}\n",
            fg=typer.colors.BRIGHT_MAGENTA,
        )



def compute_feature_contribution(resource_monitor: Optional["ResourceMonitor"] = None) -> None:
    """Compute feature contribution for the symreg model.

    Args:
        resource_monitor (ResourceMonitor, optional): Resource monitor object. Defaults to None.
    """
    start_time = time.time()
    typer.secho("Computing feature contribution for symreg", fg=typer.colors.BRIGHT_GREEN)

    # Only calculate for symreg model
    each_model = "symreg"

    # Load the model
    reg_model_file = os.path.join(script_dir, f"data/ml_models/{each_model}.json")
    with open(reg_model_file, "r") as json_file:
        model_dict = json.load(json_file)

    # Load the test data
    df_test = pd.read_csv(f"{tmp_dir_path}/{each_model}_hits_all_models.tsv", sep="\t")

    # Create X_test without 'taxon_oid'
    taxon_ids = df_test["taxon_oid"]
    X_test = df_test.drop(columns=["taxon_oid"])

    # Get feature names
    feature_names = X_test.columns.tolist()

    # Load model from JSON
    model = xgb.XGBRegressor()
    model.load_model(reg_model_file)

    # Calculate SHAP values
    explainer = _build_shap_explainer(model, X_test)
    shap_values = explainer(X_test)

    # Create the feature contribution DataFrame (sum of absolute SHAP values)
    feature_contribution = pd.DataFrame({
        "feature": feature_names,
        f"mean_abs_shap_{each_model}": np.abs(shap_values.values).mean(axis=0)
    })

    # Save to file
    feature_contribution.to_csv(
        savedir + f"/feature_contribution_{each_model}.tsv", sep="\t", index=False
    )

    # Create melted shap values for visualization and further analysis
    shap_melt = pd.DataFrame()
    for i in range(len(taxon_ids)):
        temp_df = pd.DataFrame({
            "taxon_oid": taxon_ids.iloc[i],
            "feature": feature_names,
            "shap_value": shap_values.values[i,:] ,
            "feature_value": X_test.iloc[i,:].values
        })
        shap_melt = pd.concat([shap_melt, temp_df])

    shap_melt.to_csv(
        savedir + f"/shap_melt_{each_model}.tsv", sep="\t", index=False
    )

    end_time = time.time()
    duration = end_time - start_time

    if resource_monitor:
        resource_monitor.log_python_task("Feature Contribution Analysis (SHAP)", duration, None, "SHAP explainer analysis")

    typer.secho(
        f"[OK] Feature contribution calculated for {each_model}\n",
        fg=typer.colors.BRIGHT_MAGENTA,
    )



def count_uni56() -> None:
    """Count the number of UNI56 markers found in each genome."""
    df_uni56 = pd.read_csv(tmp_dir_path + "/uni56_hits_all_models.tsv", sep="\t")
    df_uni56 = df_uni56.set_index("taxon_oid", drop=True)
    df_uni56[df_uni56 > 0] = 1
    df_uni56["total_UNI56"] = df_uni56.sum(axis=1)
    df_uni56["completeness_UNI56"] = (100 * (df_uni56["total_UNI56"] / 56)).round(2)
    df_uni56.to_csv(tmp_dir_path + "/uni56_presence.tsv", sep="\t", index=True)



def remove_temp_files() -> None:
    """Remove the temporary files directory."""
    typer.secho(message="Removing tmp folder\n", fg=typer.colors.BRIGHT_GREEN)
    shutil.rmtree(tmp_dir_path)


def calculate_weighted_distances(resource_monitor: Optional["ResourceMonitor"] = None) -> None:
    """
    Calculate weighted euclidean distances for symreg and symcla models.
    This function calculates the minimum weighted distance between each submitted genome
    and the rows in the training set for both symreg and symcla models.
    """
    start_time = time.time()
    typer.secho("Calculating weighted distances", fg=typer.colors.BRIGHT_GREEN)

    # Process both models: symreg and symcla
    for model_type in ["REG", "CLA"]:
        # Load the feature importance file with relative path
        feat_imp = pd.read_csv(
            os.path.join(script_dir, f"data/arrays/feature_importance_{model_type}.tsv"),
            sep="\t"
        )

        # Load the training set with relative path
        train_df = pd.read_csv(
            os.path.join(script_dir, f"data/arrays/array_{model_type}.tsv"),
            sep="\t"
        )

        # Load the test data
        test_df = pd.read_csv(
            f"{tmp_dir_path}/sym{model_type.lower()}_hits_all_models.tsv",
            sep="\t"
        )

        # Extract feature columns (columns starting with "OG")
        feature_cols = [col for col in train_df.columns if col.startswith("OG")]

        # Get feature weights in the same order as feature_cols
        feature_weights = np.array([
            feat_imp.loc[feat_imp['feature'] == col, 'importance'].values[0]
            for col in feature_cols
        ])

        # Calculate the square root of weights for weighted distance calculation
        weight_sqrt = np.sqrt(feature_weights)

        # Extract matrix from test and train dataframes
        train_matrix = train_df[feature_cols].values  # shape: (n_train, n_features)
        test_matrix = test_df[test_df.columns.intersection(feature_cols)].values  # shape: (n_test, n_features)

        # Apply weights to the feature matrices
        train_tilde = train_matrix * weight_sqrt  # weighted training features
        test_tilde = test_matrix * weight_sqrt    # weighted test features

        # Calculate weighted euclidean distances
        # First calculate the squared norms for each row
        train_norm2_weighted = np.sum(train_tilde**2, axis=1)  # shape: (n_train,)
        test_norm2_weighted = np.sum(test_tilde**2, axis=1)    # shape: (n_test,)

        # Use the identity: ||x - y||^2 = ||x||^2 + ||y||^2 - 2*(x . y)
        d2_weighted = np.add.outer(test_norm2_weighted, train_norm2_weighted) - 2 * np.dot(test_tilde, train_tilde.T)
        d2_weighted = np.maximum(d2_weighted, 0)  # ensure no negative values due to numeric errors

        # For each test sample, take the minimum squared distance across all training samples and calculate sqrt
        min_sq_dist_weighted = np.min(d2_weighted, axis=1)
        min_distances_weighted = np.sqrt(min_sq_dist_weighted)

        # Create a result dataframe
        result_df = pd.DataFrame({
            'taxon_oid': test_df['taxon_oid'],
            f'min_distance_weighted_{model_type}': min_distances_weighted
        })

        # Save the result to a file
        result_path = f"{tmp_dir_path}/min_distances_{model_type.lower()}.tsv"
        result_df.to_csv(result_path, sep="\t", index=False)
        typer.secho(f"[OK] Calculated weighted distances for {model_type}\n", fg=typer.colors.BRIGHT_MAGENTA)

    end_time = time.time()
    duration = end_time - start_time

    if resource_monitor:
        resource_monitor.log_python_task("Weighted Distance Calculation", duration, None, "Distance matrix computation")


def apply_neural_network(resource_monitor: Optional["ResourceMonitor"] = None) -> None:
    """
    Apply the neural network to produce the final classification with confidence score.
    The neural network model uses the following features:
    - prediction_REG (symreg score)
    - prediction_CLA_proba_* (probabilities from symcla)
    - completeness (UNI56 completeness)
    - min_distance_weighted_REG
    - min_distance_weighted_CLA
    """
    start_time = time.time()
    typer.secho("Applying neural network for final classification", fg=typer.colors.BRIGHT_GREEN)

    try:
        # Force TensorFlow to use CPU only
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

    except Exception:
        typer.secho(
            "Error: Required libraries not installed. Please install tensorflow and joblib.",
            fg=typer.colors.BRIGHT_RED,
            err=True,
        )
        exit(1)

    # Load the model and scaler using absolute paths based on script location
    try:
        nn_model_path = os.path.join(script_dir, "data/ml_models/NN_model_big.keras")
        nn_scaler_path = os.path.join(script_dir, "data/ml_models/NN_scaler_big.pkl")
        loaded_model = load_model(nn_model_path)
        loaded_scaler = joblib.load(nn_scaler_path)
    except (OSError, IOError) as e:
        typer.secho(
            f"Error loading neural network model or scaler: {str(e)}",
            fg=typer.colors.BRIGHT_RED,
            err=True,
        )
        exit(1)

    # Load the required data files
    reg_predictions = pd.read_csv(f"{tmp_dir_path}/symreg_predictions.tsv", sep="\t")
    cla_predictions = pd.read_csv(f"{tmp_dir_path}/symcla_predictions.tsv", sep="\t")
    uni56_presence = pd.read_csv(f"{tmp_dir_path}/uni56_presence.tsv", sep="\t")

    # Load distance files
    distance_reg = pd.read_csv(f"{tmp_dir_path}/min_distances_reg.tsv", sep="\t")
    distance_cla = pd.read_csv(f"{tmp_dir_path}/min_distances_cla.tsv", sep="\t")

    # Prepare the input data for the neural network
    input_data = pd.DataFrame({
        'taxon_oid': reg_predictions['taxon_oid'],
        'prediction_REG': reg_predictions['symreg_score'],
        'prediction_CLA_proba_0': cla_predictions['proba_fl'],
        'prediction_CLA_proba_1': cla_predictions['proba_ha'],
        'prediction_CLA_proba_2': cla_predictions['proba_in'],
        'completeness': uni56_presence['completeness_UNI56'],
        'min_distance_weighted_REG': distance_reg[f'min_distance_weighted_REG'],
        'min_distance_weighted_CLA': distance_cla[f'min_distance_weighted_CLA']
    })

    # Make predictions using the neural network
    nn_results = predict_new_data(input_data, model=loaded_model, scaler=loaded_scaler)

    # Map predicted_label to class names
    label_map = {0: "Free-living", 1: "Symbiont;Host-associated", 2: "Symbiont;Obligate-intracellular"}
    nn_results['predicted_class'] = nn_results['predicted_label'].map(label_map)

    # Save the neural network results
    nn_results.to_csv(f"{tmp_dir_path}/nn_predictions.tsv", sep="\t", index=False)

    # Create a simplified output dataframe
    output_df = pd.DataFrame({
        'taxon_oid': nn_results['taxon_oid'],
        'completeness_UNI56': uni56_presence['completeness_UNI56'].round(2),
        # 'prob_Free_living': [prob[0] for prob in nn_results['probabilities']],
        # 'prob_Symbiont_Host_associated': [prob[1] for prob in nn_results['probabilities']],
        # 'prob_Symbiont_Obligate_intracellular': [prob[2] for prob in nn_results['probabilities']],
        'classification': nn_results['predicted_class'],
        'confidence': nn_results['confidence'],
    })

    # Rename the genome names back to the original names
    genome_dict_path = f"{tmp_dir_path}/genomes_dict.json"
    with open(genome_dict_path, "r") as infile:
        genome_dict = json.load(infile)

    output_df['taxon_oid'] = output_df['taxon_oid'].replace(genome_dict)

    # Save the final simplified output
    print(output_df)
    output_df.to_csv(f"{savedir}/symclatron_results.tsv", sep="\t", index=False)

    end_time = time.time()
    duration = end_time - start_time

    if resource_monitor:
        resource_monitor.log_python_task("Neural Network Classification", duration, None, "Deep learning inference")

    typer.secho(
        f"[OK] Neural network classification completed\n",
        fg=typer.colors.BRIGHT_MAGENTA,
    )

def predict_with_neural_network_batch(model: Any, scaler: Any, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, List[List[float]]]:
    """
    Make predictions using the trained neural network model for a batch of data.

    Parameters:
    model: Trained neural network model
    scaler: Fitted StandardScaler
    df (pandas.DataFrame): A dataframe of multiple data points

    Returns:
    tuple: (predictions, confidences, probabilities_list)
    """

    # Prepare features for all rows at once
    features = np.stack([
        df['prediction_REG'].values,
        df['prediction_CLA_proba_0'].values,
        df['prediction_CLA_proba_1'].values,
        df['prediction_CLA_proba_2'].values,
        df['completeness'].values,
        df['min_distance_weighted_REG'].values,
        df['min_distance_weighted_CLA'].values
    ], axis=1)

    # Standardize features
    features_scaled = scaler.transform(features)

    # Get model predictions for all rows
    probabilities = model.predict(features_scaled)
    predictions = np.argmax(probabilities, axis=1)

    # Get confidence for each prediction (probability of the predicted class)
    confidences = np.array([probabilities[i, pred] for i, pred in enumerate(predictions)])

    # Adjust confidence based on distance and completeness - vectorized
    distance_factor = np.ones(len(df))
    mask_distance = (df['min_distance_weighted_CLA'] > 80) | (df['min_distance_weighted_REG'] > 80)
    distance_factor[mask_distance] = 0.8

    completeness_factor = np.ones(len(df))
    mask_completeness = df['completeness'] < 50
    completeness_factor[mask_completeness] = 0.8

    adjusted_confidences = confidences * distance_factor * completeness_factor

    # Convert probabilities to list of lists
    probabilities_list = [prob.tolist() for prob in probabilities]

    return predictions.astype(int), adjusted_confidences, probabilities_list

def predict_new_data(new_data: pd.DataFrame, model: Any = None, scaler: Any = None) -> pd.DataFrame:
    """
    Make predictions on new data with confidence scores.

    Parameters:
    new_data (DataFrame): New data to predict
    model: Neural network model
    scaler: Feature scaler

    Returns:
    DataFrame: Original data with predictions and confidence scores
    """
    result_df = new_data.copy()

    # Use the batch prediction function
    predictions, confidences, probabilities_list = predict_with_neural_network_batch(model, scaler, new_data)

    # Add results to the dataframe
    result_df['predicted_label'] = predictions
    result_df['confidence'] = confidences
    result_df['probabilities'] = probabilities_list

    return result_df


def setup_logging(log_file: Optional[str] = None) -> logging.Logger:
    """
    Configure logging for the application.

    Parameters:
    log_file (str, optional): Path to the log file. If not provided, logs will only go to console.

    Returns:
    logging.Logger: Configured logger object
    """
    logger = logging.getLogger('symclatron')
    logger.setLevel(logging.INFO)

    # Create formatters
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(message)s')

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # Add console handler to logger
    logger.addHandler(console_handler)

    # If log file is provided, create file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # DEBUG level for file (more verbose)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # Prevent log messages from being propagated to the root logger
    logger.propagate = False

    return logger


def validate_input(genome_dir: str, logger: logging.Logger) -> bool:
    """
    Validate input data before processing.

    Parameters:
    genome_dir (str): Directory containing the genome files to be classified
    logger (logging.Logger): Logger object for logging messages

    Returns:
    bool: True if validation passes, False otherwise
    """
    logger.info("Validating input data...")

    # Check if the genome directory exists
    if not os.path.exists(genome_dir):
        logger.error(f"Genome directory '{genome_dir}' does not exist")
        typer.secho(
            f"[Error] Genome directory '{genome_dir}' does not exist",
            fg=typer.colors.BRIGHT_RED,
            err=True,
        )
        exit(1)

    # Check if the directory contains any .faa files
    faa_files = glob.glob(os.path.join(genome_dir, "*.faa"))
    if not faa_files:
        logger.error(f"No .faa files found in '{genome_dir}'")
        typer.secho(
            f"[Error] No .faa files found in '{genome_dir}'",
            fg=typer.colors.BRIGHT_RED,
            err=True,
        )
        exit(1)

    # Validate each .faa file to ensure it's a valid FASTA file
    invalid_files = []
    empty_files = []

    logger.info(f"Found {len(faa_files)} genome files to validate")
    for faa_file in faa_files:
        file_size = os.path.getsize(faa_file)

        # Check if file is empty
        if file_size == 0:
            empty_files.append(os.path.basename(faa_file))
            continue

        # Check if file is a valid FASTA file
        with open(faa_file, 'r') as f:
            first_line = f.readline().strip()
            if not first_line.startswith('>'):
                invalid_files.append(os.path.basename(faa_file))

    # Report and exit if any files are invalid
    if empty_files:
        logger.error(f"Found {len(empty_files)} empty files: {', '.join(empty_files)}")
        typer.secho(
            f"[Error] Found {len(empty_files)} empty files: {', '.join(empty_files)}",
            fg=typer.colors.BRIGHT_RED,
            err=True,
        )
        exit(1)

    if invalid_files:
        logger.error(f"Found {len(invalid_files)} invalid FASTA files: {', '.join(invalid_files)}")
        typer.secho(
            f"[Error] Found {len(invalid_files)} invalid FASTA files: {', '.join(invalid_files)}",
            fg=typer.colors.BRIGHT_RED,
            err=True,
        )
        exit(1)

    logger.info(f"All {len(faa_files)} genome files are valid")
    return True


def generate_classification_summary(output_dir: str, logger: logging.Logger) -> None:
    """
    Generate a summary report of classification results.

    Parameters:
    output_dir (str): Directory where results are saved
    logger (logging.Logger): Logger for logging messages
    """
    try:
        # Load the neural network classification results
        results_file = f"{output_dir}/symclatron_results.tsv"
        if not os.path.exists(results_file):
            logger.warning("Results file not found. Cannot generate summary.")
            return

        results_df = pd.read_csv(results_file, sep="\t")

        # Count genomes in each classification category
        if 'classification' in results_df.columns:
            class_counts = results_df['classification'].value_counts()

            # Calculate completeness statistics
            completeness_stats = {}
            if 'completeness_UNI56' in results_df.columns:
                completeness_stats = {
                    'mean': round(results_df['completeness_UNI56'].mean(), 2),
                    'median': round(results_df['completeness_UNI56'].median(), 2),
                    'min': round(results_df['completeness_UNI56'].min(), 2),
                    'max': round(results_df['completeness_UNI56'].max(), 2)
                }

            # Calculate confidence statistics
            confidence_stats = {}
            if 'confidence' in results_df.columns:
                confidence_stats = {
                    'mean': results_df['confidence'].mean(),
                    'median': results_df['confidence'].median(),
                    'min': results_df['confidence'].min(),
                    'max': results_df['confidence'].max()
                }

            # Create summary text for console
            logger.info("=" * 60)
            logger.info("Classification Summary")
            logger.info("=" * 60)
            logger.info(f"Total genomes analyzed: {len(results_df)}")
            logger.info("\nClassification counts:")
            for category, count in class_counts.items():
                percentage = (count / len(results_df)) * 100
                logger.info(f"  - {category}: {count} ({percentage:.1f}%)")

            logger.info("\nCompleteness statistics (UNI56 markers):")
            logger.info(f"  - Mean: {completeness_stats.get('mean', 'N/A'):.2f}%")
            logger.info(f"  - Median: {completeness_stats.get('median', 'N/A'):.2f}%")
            logger.info(f"  - Min: {completeness_stats.get('min', 'N/A'):.2f}%")
            logger.info(f"  - Max: {completeness_stats.get('max', 'N/A'):.2f}%")

            logger.info("\nConfidence statistics:")
            logger.info(f"  - Mean: {confidence_stats.get('mean', 'N/A'):.2f}")
            logger.info(f"  - Median: {confidence_stats.get('median', 'N/A'):.2f}")
            logger.info(f"  - Min: {confidence_stats.get('min', 'N/A'):.2f}")
            logger.info(f"  - Max: {confidence_stats.get('max', 'N/A'):.2f}")

            # Create a formal summary file
            summary_file = f"{output_dir}/classification_summary.txt"
            with open(summary_file, 'w') as f:
                f.write("SYMCLATRON CLASSIFICATION SUMMARY\n")
                f.write("=" * 40 + "\n\n")
                f.write(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                f.write(f"Total genomes analyzed: {len(results_df)}\n\n")

                f.write("CLASSIFICATION COUNTS\n")
                f.write("-" * 30 + "\n")
                for category, count in class_counts.items():
                    percentage = (count / len(results_df)) * 100
                    f.write(f"{category}: {count} ({percentage:.1f}%)\n")

                f.write("\nCOMPLETENESS STATISTICS (UNI56 MARKERS)\n")
                f.write("-" * 30 + "\n")
                f.write(f"Mean: {completeness_stats.get('mean', 'N/A'):.2f}%\n")
                f.write(f"Median: {completeness_stats.get('median', 'N/A'):.2f}%\n")
                f.write(f"Min: {completeness_stats.get('min', 'N/A'):.2f}%\n")
                f.write(f"Max: {completeness_stats.get('max', 'N/A'):.2f}%\n")

                f.write("\nCONFIDENCE STATISTICS\n")
                f.write("-" * 30 + "\n")
                f.write(f"Mean: {confidence_stats.get('mean', 'N/A'):.2f}\n")
                f.write(f"Median: {confidence_stats.get('median', 'N/A'):.2f}\n")
                f.write(f"Min: {confidence_stats.get('min', 'N/A'):.2f}\n")
                f.write(f"Max: {confidence_stats.get('max', 'N/A'):.2f}\n")

            logger.info(f"\nSummary saved to: {summary_file}")
            logger.info("=" * 60)

        else:
            logger.warning("Classification column not found in results. Cannot generate complete summary.")

    except Exception as e:
        logger.error(f"Error generating classification summary: {str(e)}")
        return


def classify(
    genome_dir: str = "input_genomes",
    save_dir: str = "output_symclatron",
    deltmp: bool = True,
    ncpus: int = 2,
    quiet: bool = False,
) -> None:
    """
    Main classification function.

    This function orchestrates the entire classification workflow, including:
    - Setting up logging and resource monitoring.
    - Validating input data.
    - Running HMMER searches.
    - Processing results and running machine learning models.
    - Generating final reports.

    Parameters:
    genome_dir (str): Directory containing genome FASTA files.
    save_dir (str): Directory to save results.
    deltmp (bool): Whether to delete temporary files.
    """
    start_time = time.time()

    global savedir
    savedir = save_dir

    # Create output directory first to ensure we have a place for logs
    if not os.path.exists(savedir):
        os.makedirs(savedir)

    # Set up logging with date and time in the log file name
    # Check if current directory is writable, if not use output directory for logs
    script_dir_writable = os.access(os.path.dirname(os.path.abspath(__file__)), os.W_OK)
    if script_dir_writable:
        log_file = f"{save_dir}_symclatron_classification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        resource_log_file = f"{save_dir}_symclatron_resources_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    else:
        log_file = f"{savedir}/symclatron_classification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        resource_log_file = f"{savedir}/symclatron_resources_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = setup_logging(log_file)

    # Initialize resource monitoring using log directory
    resource_monitor = ResourceMonitor(os.path.dirname(resource_log_file))

    # Rest of the function remains unchanged
    logger.info("Starting symclatron classifier")
    if not quiet:
        greetings()
        init_message_classify()

    script_path = Path(__file__)
    script_dir = script_path.parent
    global data_folder_path
    data_folder_path = Path(script_dir) / "data"
    logger.debug(f"Data folder path: {data_folder_path}")

    global tmp_dir_path
    tmp_dir_path = f"{savedir}/tmp"
    create_tmp_dir(logger)

    global genomedir
    genomedir = genome_dir
    logger.info(f"Using genomes from: {genomedir}")

    # Validate input data before processing
    validate_input(genome_dir, logger)

    logger.info("Copying genomes to temporary directory")
    tmp_genomes_path = copy_genomes_to_tmp_dir()

    logger.info("Renaming genomes")
    rename_genomes(tmp_genome_dir_path=tmp_genomes_path)

    logger.info("Renaming proteins in FASTA files")
    rename_all_proteins_in_fasta_files(
        tmp_genome_dir_path=tmp_genomes_path, savedir=savedir
    )

    logger.info("Merging genomes")
    merge_genomes(tmp_genomes_path)

    logger.info("Running hmmsearch for symclatron models")
    run_hmmsearch(ncpus=ncpus, resource_monitor=resource_monitor)

    logger.info("Running hmmsearch for UNI56 markers")
    run_hmmsearch_uni56(ncpus=ncpus, resource_monitor=resource_monitor)

    logger.info("Saving models list")
    save_list_of_models()

    logger.info("Saving genomes list")
    save_list_of_genomes(tmp_genomes_path=tmp_genomes_path)

    logger.info("Processing hmmsearch results")
    hmmer_results_to_pandas_df()

    logger.info("Splitting features for different models")
    split_hits_all_models_for_3_models()

    logger.info("Running classification models")
    classify_genomes_internal(resource_monitor)

    logger.info("Computing feature contributions")
    compute_feature_contribution(resource_monitor)

    logger.info("Counting UNI56 markers")
    count_uni56()

    # Calculate weighted distances for REG and CLA models
    logger.info("Calculating weighted distances")
    calculate_weighted_distances(resource_monitor)

    # Apply neural network for final classification
    logger.info("Applying neural network for final classification")
    apply_neural_network(resource_monitor)

    # Generate summary report
    logger.info("Generating classification summary report")
    generate_classification_summary(savedir, logger)

    # Only keep the simplified output and remove hostcla-related files
    logger.info("Cleaning up output files")
    if os.path.exists(f"{savedir}/feature_contribution_hostcla.tsv"):
        os.remove(f"{savedir}/feature_contribution_hostcla.tsv")

    if os.path.exists(f"{savedir}/shap_melt_hostcla.tsv"):
        os.remove(f"{savedir}/shap_melt_hostcla.tsv")

    if deltmp:
        logger.info("Removing temporary files")
        remove_temp_files()
    else:
        logger.info("Keeping temporary files for inspection")

    # end timer
    end_time = time.time()
    execution_time_secs = round(end_time - start_time)
    execution_time_mins = round((end_time - start_time)/60, 1)

    logger.info(f"Classification completed in {execution_time_secs} seconds ({execution_time_mins} minutes)")
    typer.secho(
        message=f"Total time: {execution_time_secs} seconds ({execution_time_mins} minutes)",
        fg=typer.colors.BRIGHT_MAGENTA,
    )

    # Finalize resource monitoring and generate report
    resource_monitor.finalize(execution_time_mins)

    # Display final resource summary
    logger.info("📊 Resource usage summary saved to resource log file")
    typer.secho(
        f"✅ Resource usage logs saved to: {resource_monitor.log_file}",
        fg=typer.colors.BRIGHT_GREEN,
    )


app = typer.Typer(
    name="symclatron",
    help="Symbiont Classifier - Machine Learning-based Classification of Microbial Symbiotic Lifestyles",
    epilog="For more information, visit: https://github.com/NeLLi-team/symclatron",
    rich_markup_mode="rich",
    add_completion=False,
    no_args_is_help=True
)



@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit"
    )
):
    """
    symclatron: Symbiont Classifier

    Machine learning-based classification of microbial symbiotic lifestyles

    This tool classifies microbial genomes into three categories:
    • Free-living
    • Symbiont; Host-associated
    • Symbiont; Obligate-intracellular
    """
    pass


@app.command("setup")
def setup_data(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-download even if data directory exists"
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress progress messages"
    )
):
    """
    Download and setup required data files.

    This command downloads the symclatron database and sets up the data directory.
    Run this once before using the classifier.
    """
    if not quiet:
        print_header()
        init_message_setup()

    # Check if data directory already exists and handle force flag
    data_dir = os.path.join(script_dir, "data")
    if os.path.isdir(data_dir) and not force:
        if not quiet:
            typer.secho("✅ Data directory already exists. Use --force to re-download.", fg=typer.colors.YELLOW)
        return

    extract_data()

    if not quiet:
        typer.secho("✅ Setup completed successfully!", fg=typer.colors.GREEN, bold=True)



@app.command("classify")
def classify_genomes(
    genome_dir: str = typer.Option(
        "input_genomes",
        "--genome-dir",
        "-i",
        help="Directory containing genome FASTA files (.faa)"
    ),
    output_dir: str = typer.Option(
        "output_symclatron",
        "--output-dir",
        "-o",
        help="Output directory for results"
    ),
    keep_tmp: bool = typer.Option(
        False,
        "--keep-tmp",
        help="Keep temporary files for debugging"
    ),
    threads: int = typer.Option(
        2,
        "--threads",
        "-t",
        min=1,
        max=32,
        help="Number of threads for HMMER searches"
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress progress messages"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show detailed progress information"
    )
):
    """
    Classify genomes into symbiotic lifestyle categories.

    This command processes protein FASTA files (.faa) and classifies each genome
    into one of three categories based on their predicted symbiotic lifestyle.
    """
    # Validate input directory
    if not os.path.isdir(genome_dir):
        typer.secho(f"❌ Error: Genome directory '{genome_dir}' does not exist", fg=typer.colors.RED)
        raise typer.Exit(1)

    # Check for .faa files
    faa_files = glob.glob(os.path.join(genome_dir, "*.faa")) + \
                glob.glob(os.path.join(genome_dir, "*.fasta")) + \
                glob.glob(os.path.join(genome_dir, "*.fa"))

    if not faa_files:
        typer.secho(f"❌ Error: No FASTA files (.faa, .fasta, .fa) found in '{genome_dir}'", fg=typer.colors.RED)
        raise typer.Exit(1)

    # Check if data directory exists
    data_dir = os.path.join(script_dir, "data")
    if not os.path.isdir(data_dir):
        typer.secho("❌ Error: Data directory not found. Run 'symclatron setup' first.", fg=typer.colors.RED)
        typer.secho("Tip: Run 'symclatron setup' to download required data files", fg=typer.colors.YELLOW)
        raise typer.Exit(1)

    if not quiet:
        print_header()
        init_message_classify()
        typer.secho(f"Input directory: {genome_dir}", fg=typer.colors.BLUE)
        typer.secho(f"Output directory: {output_dir}", fg=typer.colors.BLUE)
        typer.secho(f"Threads: {threads}", fg=typer.colors.BLUE)
        typer.secho(f"Found {len(faa_files)} genome files", fg=typer.colors.BLUE)

        if keep_tmp:
            typer.secho("Temporary files will be preserved", fg=typer.colors.YELLOW)

    # Call the original classify function with updated parameters
    classify(
        genome_dir=genome_dir,
        save_dir=output_dir,
        deltmp=not keep_tmp,
        ncpus=threads,
        quiet=quiet,  # Pass quiet parameter to avoid redundant headers
    )


@app.command("test")
def run_test(
    keep_tmp: bool = typer.Option(
        False,
        "--keep-tmp",
        help="Keep temporary files after test"
    ),
    output_dir: str = typer.Option(
        "test_output_symclatron",
        "--output-dir",
        "-o",
        help="Output directory for test results"
    )
):
    """
    Run symclatron with test genomes.

    This command runs a quick test using the provided test genomes
    to verify that symclatron is working correctly.
    """
    test_genome_dir = os.path.join(script_dir, "data", "test_genomes")

    if not os.path.isdir(test_genome_dir):
        typer.secho("❌ Error: Test genomes not found. Run 'symclatron setup' first.", fg=typer.colors.RED)
        raise typer.Exit(1)

    print_header()
    typer.secho("Running test with provided genomes...", fg=typer.colors.BLUE, bold=True)

    classify_genomes(
        genome_dir=test_genome_dir,
        output_dir=output_dir,
        keep_tmp=keep_tmp,
        threads=2,
        quiet=True,  # Suppress redundant headers since we already printed them
        verbose=False
    )




if __name__ == "__main__":
    app()
