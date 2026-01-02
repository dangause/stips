#!/bin/bash
# Assess pipeline run success/failure rates

LOG_DIR="$1"

if [[ -z "$LOG_DIR" || ! -d "$LOG_DIR" ]]; then
    echo "Usage: $0 <log_directory>"
    echo "Example: $0 logs/dia_multiband_20260102_154433_24534"
    exit 1
fi

echo "========================================="
echo "Pipeline Run Assessment"
echo "========================================="
echo "Log directory: $LOG_DIR"
echo ""

# Science processing assessment
echo "=== SCIENCE PROCESSING ==="
if [[ -d "$LOG_DIR/science" ]]; then
    total_science_nights=0
    total_science_failures=0

    for night_dir in "$LOG_DIR/science"/*; do
        if [[ -d "$night_dir" ]]; then
            night=$(basename "$night_dir")
            log_file="$night_dir/science.log"

            if [[ -f "$log_file" ]]; then
                ((total_science_nights++))

                # Get final execution summary
                final_line=$(grep "Executed.*quanta successfully" "$log_file" | tail -1)

                if [[ -n "$final_line" ]]; then
                    success=$(echo "$final_line" | grep -oE 'Executed [0-9]+' | awk '{print $2}')
                    failed=$(echo "$final_line" | grep -oE '[0-9]+ failed' | awk '{print $1}')
                    total=$(echo "$final_line" | grep -oE 'total [0-9]+' | awk '{print $2}')

                    success_rate=$(awk "BEGIN {printf \"%.1f\", ($success/$total)*100}")

                    # Count specific error types
                    no_matches=$(grep -c "No matches found" "$log_file" 2>/dev/null || echo 0)
                    not_enough=$(grep -c "Not enough catalog objects" "$log_file" 2>/dev/null || echo 0)

                    echo "  $night: $success/$total succeeded ($success_rate%) [NoMatch:$no_matches, Sparse:$not_enough]"

                    total_science_failures=$((total_science_failures + failed))
                else
                    echo "  $night: No execution summary found"
                fi
            fi
        fi
    done

    echo ""
    echo "Science nights processed: $total_science_nights"
    echo "Total failures across all science nights: $total_science_failures"
else
    echo "No science logs found"
fi

echo ""

# Template processing assessment
echo "=== TEMPLATE BUILDING ==="
if [[ -d "$LOG_DIR/templates" ]]; then
    template_count=0
    template_success=0
    template_fail=0

    for template_log in $(find "$LOG_DIR/templates" -name "*.log"); do
        ((template_count++))
        band_tract=$(echo "$template_log" | grep -oE '(b|v|r|i)/tract_[0-9]+' || echo "unknown")

        if grep -q "completed successfully" "$template_log" 2>/dev/null; then
            ((template_success++))
            status="✓ SUCCESS"
        elif grep -q "ERROR\|failed\|FATAL" "$template_log" 2>/dev/null; then
            ((template_fail++))
            status="✗ FAILED"

            # Get error details
            error_type=$(grep -oE "MatcherFailure|MeasureApCorrError|No matches|Not enough" "$template_log" | head -1)
            if [[ -n "$error_type" ]]; then
                status="✗ FAILED ($error_type)"
            fi
        else
            status="? UNKNOWN"
        fi

        # Get execution stats if available
        final_stats=$(grep "Executed.*quanta successfully" "$template_log" | tail -1)
        if [[ -n "$final_stats" ]]; then
            success=$(echo "$final_stats" | grep -oE 'Executed [0-9]+' | awk '{print $2}')
            failed=$(echo "$final_stats" | grep -oE '[0-9]+ failed' | awk '{print $1}')
            total=$(echo "$final_stats" | grep -oE 'total [0-9]+' | awk '{print $2}')
            stats_str="($success/$total succeeded)"
        else
            stats_str=""
        fi

        echo "  $band_tract: $status $stats_str"
    done

    echo ""
    echo "Templates processed: $template_count"
    echo "  Successful: $template_success"
    echo "  Failed: $template_fail"
else
    echo "No template logs found"
fi

echo ""

# DIA processing assessment
echo "=== DIFFERENCE IMAGING (DIA) ==="
if [[ -d "$LOG_DIR/dia" ]]; then
    total_dia_nights=0
    total_dia_bands=0
    dia_success=0
    dia_fail=0

    for night_dir in "$LOG_DIR/dia"/*; do
        if [[ -d "$night_dir" ]]; then
            night=$(basename "$night_dir")
            ((total_dia_nights++))

            for band_dir in "$night_dir"/*; do
                if [[ -d "$band_dir" ]]; then
                    band=$(basename "$band_dir")
                    log_file="$band_dir/dia.log"

                    if [[ -f "$log_file" ]]; then
                        ((total_dia_bands++))

                        # Check for completion
                        if grep -q "completed successfully" "$log_file" 2>/dev/null; then
                            ((dia_success++))
                            status="✓"
                        elif grep -q "ERROR\|failed\|FATAL" "$log_file" 2>/dev/null; then
                            ((dia_fail++))
                            status="✗"

                            # Get error summary
                            error_summary=$(grep -E "ERROR.*Exception|failed.*Exception" "$log_file" | head -1 | cut -d: -f3- | cut -c1-60)
                        else
                            status="?"
                        fi

                        # Get execution stats
                        final_stats=$(grep "Executed.*quanta successfully" "$log_file" | tail -1)
                        if [[ -n "$final_stats" ]]; then
                            success=$(echo "$final_stats" | grep -oE 'Executed [0-9]+' | awk '{print $2}')
                            failed=$(echo "$final_stats" | grep -oE '[0-9]+ failed' | awk '{print $1}')
                            total=$(echo "$final_stats" | grep -oE 'total [0-9]+' | awk '{print $2}')

                            if [[ $total -gt 0 ]]; then
                                success_rate=$(awk "BEGIN {printf \"%.0f\", ($success/$total)*100}")
                                echo "  $night/$band: $status $success/$total ($success_rate%)"
                            else
                                echo "  $night/$band: $status (no quanta)"
                            fi
                        else
                            echo "  $night/$band: $status (no stats)"
                        fi
                    fi
                fi
            done
        fi
    done

    echo ""
    echo "DIA nights processed: $total_dia_nights"
    echo "DIA night/band combinations: $total_dia_bands"
    if [[ $total_dia_bands -gt 0 ]]; then
        dia_success_rate=$(awk "BEGIN {printf \"%.1f\", ($dia_success/$total_dia_bands)*100}")
        echo "  Successful: $dia_success ($dia_success_rate%)"
        echo "  Failed: $dia_fail"
    fi
else
    echo "No DIA logs found"
fi

echo ""
echo "========================================="
echo "Assessment complete"
echo "========================================="
