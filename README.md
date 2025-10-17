<!-- example to run the profiler with profiler's parameters and target program's parameters -->
python3 profiler_system/analyzer.py sar_colorization.py \
    --metrics_interval_ms 500 \
    --output_dir . \
    --csv_write_interval_s 5 \
    -- \
    --sar_dir prepared_dataset/train/sar/ \
    --optical_dir prepared_dataset/train/optical/ \
    --n_epochs 2 \
    --batch_size 16 \
    --img_size 256 \
    --checkpoint_interval 10
<!-- The "--" is used to seperate parameters of profiler and that of target program -->
