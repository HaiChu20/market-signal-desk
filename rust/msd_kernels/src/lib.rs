use pyo3::prelude::*;

#[derive(Clone, Copy)]
struct Hit {
    outcome: i8, exit_index: isize, fill: f64, exit: f64,
    net_r: f64, gross_r: f64, rollovers: i64, entry_index: isize, planned_risk: f64,
    stats: [u32; 4], // ambiguous, resolved_tp, resolved_sl, unresolved
}

fn no_fill() -> Hit {
    Hit { outcome: -2, exit_index: -1, fill: f64::NAN, exit: f64::NAN,
          net_r: f64::NAN, gross_r: f64::NAN, rollovers: 0, entry_index: -1, planned_risk: f64::NAN,
          stats: [0; 4] }
}

fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let y = year - i64::from(month <= 2);
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let mp = month + if month > 2 { -3 } else { 9 };
    let doy = (153 * mp + 2) / 5 + day - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

fn civil_from_days(days: i64) -> (i64, i64, i64) {
    let z = days + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut year = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    year += i64::from(month <= 2);
    (year, month, day)
}

fn weekday_sunday_zero(days: i64) -> i64 { (days + 4).rem_euclid(7) }

fn nth_sunday(year: i64, month: i64, nth: i64) -> i64 {
    let first = days_from_civil(year, month, 1);
    let first_sunday = 1 + (7 - weekday_sunday_zero(first)).rem_euclid(7);
    days_from_civil(year, month, first_sunday + (nth - 1) * 7)
}

fn is_dst_utc(timestamp: i64) -> bool {
    let (year, _, _) = civil_from_days(timestamp.div_euclid(86400));
    let begins = nth_sunday(year, 3, 2) * 86400 + 7 * 3600;
    let ends = nth_sunday(year, 11, 1) * 86400 + 6 * 3600;
    timestamp >= begins && timestamp < ends
}

fn rollover_count(start: i64, end: i64, crypto: bool) -> i64 {
    if end <= start { return 0; }
    if crypto {
        let first = start.div_euclid(86400) + 1;
        let last = end.div_euclid(86400);
        return (last - first + 1).max(0);
    }
    let mut day = start.div_euclid(86400) - 1;
    let last_day = end.div_euclid(86400) + 1;
    let mut count = 0;
    while day <= last_day {
        let weekday_mon0 = (day + 3).rem_euclid(7);
        if weekday_mon0 < 5 {
            let daylight_probe = day * 86400 + 21 * 3600;
            let boundary = day * 86400 + if is_dst_utc(daylight_probe) { 21 * 3600 } else { 22 * 3600 };
            if start < boundary && boundary <= end {
                count += if weekday_mon0 == 4 { 3 } else { 1 };
            }
        }
        day += 1;
    }
    count
}

fn quote(row: &[f64; 8], side: i8) -> (f64, f64, f64, f64) {
    if side > 0 { (row[0], row[1], row[2], row[3]) }
    else { (row[4], row[5], row[6], row[7]) }
}

fn second_resolution(rows: &[[f64; 8]], stamps: &[i64], minute: i64,
                     side: i8, sl: f64, tp: f64) -> Option<(i8, f64)> {
    if rows.len() != stamps.len() { return None; }
    let start = stamps.partition_point(|stamp| *stamp < minute);
    if start + 60 > stamps.len() { return None; }
    // A partial second stream cannot establish which threshold was first.
    if (0..60).any(|offset| stamps[start + offset] != minute + offset as i64) { return None; }
    for row in &rows[start..start + 60] {
        let (op, high, low, _) = quote(row, side);
        let stop = if side > 0 { low <= sl } else { high >= sl };
        let target = if side > 0 { high >= tp } else { low <= tp };
        if stop { return Some((-1, if side > 0 { op.min(sl) } else { op.max(sl) })); }
        if target { return Some((1, tp)); }
    }
    None
}

// The single implementation used by scalar and batch entry points.
fn simulate_one(rows: &[[f64; 8]], timestamps: &[i64], signal_index: usize, side: i8,
                signal_price: f64, sl: f64, tp: Option<f64>, delay_bars: usize,
                deadline_ts: Option<i64>, financing_per_rollover: f64, limit_price: Option<f64>,
                expiry_ts: Option<i64>, crypto: bool, legacy_max_bars: Option<usize>,
                seconds: Option<(&[[f64; 8]], &[i64])>) -> Hit {
    let n = rows.len();
    if n == 0 || timestamps.len() != n || signal_index >= n || side == 0 || !sl.is_finite() || !signal_price.is_finite() {
        return no_fill();
    }
    if legacy_max_bars == Some(0) { return no_fill(); }
    let direction = if side > 0 { 1.0 } else { -1.0 };
    let mut entry_index = signal_index.saturating_add(delay_bars);
    if entry_index >= n || direction * (signal_price - sl) <= 0.0 { return no_fill(); }
    let mut fill_price = f64::NAN;
    let planned_risk;
    if let Some(limit) = limit_price {
        if !limit.is_finite() || direction * (limit - sl) <= 0.0 { return no_fill(); }
        let mut found = false;
        for i in entry_index..n {
            if expiry_ts.map(|x| timestamps[i] >= x).unwrap_or(false) { break; }
            let touched = if side > 0 { rows[i][6] <= limit } else { rows[i][1] >= limit };
            if touched {
                entry_index = i;
                fill_price = if side > 0 { rows[i][4].min(limit) } else { rows[i][0].max(limit) };
                found = true;
                break;
            }
        }
        if !found { return no_fill(); }
        planned_risk = (limit - sl).abs();
    } else {
        fill_price = if side > 0 { rows[entry_index][4] } else { rows[entry_index][0] };
        let mid = (rows[entry_index][0] + rows[entry_index][4]) / 2.0;
        planned_risk = (mid - sl).abs();
    }
    if !planned_risk.is_finite() || planned_risk <= 0.0 { return no_fill(); }
    let mut deadline = deadline_ts;
    if let Some(max_bars) = legacy_max_bars {
        let end_index = signal_index.saturating_add(delay_bars).saturating_add(max_bars).min(n - 1);
        deadline = Some(timestamps[end_index]);
    }
    let mut result: Option<(i8, usize, f64)> = None;
    let mut stats = [0_u32; 4];
    for i in entry_index..n {
        if deadline.map(|x| timestamps[i] >= x).unwrap_or(false) {
            let (op, _, _, _) = quote(&rows[i], side);
            result = Some((0, i, op));
            break;
        }
        let (op, high, low, close) = quote(&rows[i], side);
        let stop_hit = if side > 0 { low <= sl } else { high >= sl };
        let tp_hit = !(limit_price.is_some() && i == entry_index) &&
            tp.map(|target| if side > 0 { high >= target } else { low <= target }).unwrap_or(false);
        if stop_hit && tp_hit {
            stats[0] += 1;
            let resolved = seconds.and_then(|(second_rows, second_stamps)|
                second_resolution(second_rows, second_stamps, timestamps[i], side, sl, tp.unwrap()));
            match resolved {
                Some((1, price)) => { stats[1] += 1; result = Some((1, i, price)); },
                Some((-1, price)) => { stats[2] += 1; result = Some((-1, i, price)); },
                _ => { stats[3] += 1; result = Some((-1, i, if side > 0 { op.min(sl) } else { op.max(sl) })); },
            }
            break;
        }
        if stop_hit {
            result = Some((-1, i, if side > 0 { op.min(sl) } else { op.max(sl) }));
            break;
        }
        // The fill bar for a limit order checks SL only; TP order is unknown.
        if tp_hit { result = Some((1, i, tp.unwrap())); break; }
        if i + 1 == n { result = Some((0, i, close)); }
    }
    let (outcome, exit_index, exit_price) = result.unwrap_or_else(|| {
        let i = n - 1;
        (0, i, quote(&rows[i], side).3)
    });
    let nights = rollover_count(timestamps[entry_index], timestamps[exit_index], crypto);
    let gross = direction * (exit_price - fill_price) / planned_risk;
    let net = gross - financing_per_rollover * nights as f64 * fill_price / planned_risk;
    Hit { outcome, exit_index: exit_index as isize, fill: fill_price, exit: exit_price,
          net_r: net, gross_r: gross, rollovers: nights, entry_index: entry_index as isize,
          planned_risk, stats }
}

fn rows_from_nested(rows: Vec<Vec<f64>>) -> PyResult<Vec<[f64; 8]>> {
    rows.into_iter().map(|row| {
        if row.len() < 8 || row[..8].iter().any(|value| !value.is_finite()) {
            return Err(pyo3::exceptions::PyValueError::new_err("rows must contain eight finite OHLC values"));
        }
        Ok([row[0],row[1],row[2],row[3],row[4],row[5],row[6],row[7]])
    }).collect()
}

fn hit_tuple(hit: Hit) -> (i8, isize, f64, f64, f64, f64, i64, isize, f64) {
    (hit.outcome, hit.exit_index, hit.fill, hit.exit, hit.net_r, hit.gross_r,
     hit.rollovers, hit.entry_index, hit.planned_risk)
}

#[pyfunction]
#[pyo3(signature = (rows, timestamps, entry_index, side, entry_price, sl, tp, max_bars=None, delay_bars=2, financing_per_night=0.0, limit_price=None, expiry_index=None, deadline_ts=None, expiry_ts=None, instrument_class="index", second_rows=None, second_timestamps=None))]
fn first_hit(rows: Vec<Vec<f64>>, timestamps: Vec<i64>, entry_index: usize, side: i8,
             entry_price: f64, sl: f64, tp: Option<f64>, max_bars: Option<usize>, delay_bars: usize,
             financing_per_night: f64, limit_price: Option<f64>, expiry_index: Option<usize>,
             deadline_ts: Option<i64>, expiry_ts: Option<i64>, instrument_class: &str,
             second_rows: Option<Vec<Vec<f64>>>, second_timestamps: Option<Vec<i64>>)
             -> PyResult<(i8, isize, f64, f64, f64, f64, i64, isize, f64)> {
    let bars = rows_from_nested(rows)?;
    let second_bars = second_rows.map(rows_from_nested).transpose()?;
    let second_data = second_bars.as_deref().zip(second_timestamps.as_deref());
    let expiry = expiry_ts.or_else(|| expiry_index.and_then(|i| timestamps.get(i).copied()));
    let crypto = instrument_class.eq_ignore_ascii_case("crypto") || instrument_class.eq_ignore_ascii_case("24x7");
    Ok(hit_tuple(simulate_one(&bars, &timestamps, entry_index, side, entry_price, sl, tp,
        delay_bars, deadline_ts, financing_per_night, limit_price, expiry, crypto, max_bars,
        second_data)))
}

#[pyfunction]
#[pyo3(signature = (rows, timestamps, entry_index, side, entry_price, sl, tp, max_bars=None, delay_bars=2, financing_per_night=0.0, limit_price=None, expiry_index=None, deadline_ts=None, expiry_ts=None, instrument_class="index", second_rows=None, second_timestamps=None))]
fn first_hit_with_stats(rows: Vec<Vec<f64>>, timestamps: Vec<i64>, entry_index: usize, side: i8,
             entry_price: f64, sl: f64, tp: Option<f64>, max_bars: Option<usize>, delay_bars: usize,
             financing_per_night: f64, limit_price: Option<f64>, expiry_index: Option<usize>,
             deadline_ts: Option<i64>, expiry_ts: Option<i64>, instrument_class: &str,
             second_rows: Option<Vec<Vec<f64>>>, second_timestamps: Option<Vec<i64>>)
             -> PyResult<Vec<f64>> {
    let bars = rows_from_nested(rows)?;
    let second_bars = second_rows.map(rows_from_nested).transpose()?;
    let second_data = second_bars.as_deref().zip(second_timestamps.as_deref());
    let expiry = expiry_ts.or_else(|| expiry_index.and_then(|i| timestamps.get(i).copied()));
    let crypto = instrument_class.eq_ignore_ascii_case("crypto") || instrument_class.eq_ignore_ascii_case("24x7");
    let hit = simulate_one(&bars,&timestamps,entry_index,side,entry_price,sl,tp,delay_bars,
        deadline_ts,financing_per_night,limit_price,expiry,crypto,max_bars,second_data);
    let base = hit_tuple(hit);
    Ok(vec![base.0 as f64,base.1 as f64,base.2,base.3,base.4,base.5,
        base.6 as f64,base.7 as f64,base.8,hit.stats[0] as f64,
        hit.stats[1] as f64,hit.stats[2] as f64,hit.stats[3] as f64])
}

#[pyfunction]
fn pivots(highs: Vec<f64>, lows: Vec<f64>, k: usize) -> PyResult<Vec<(usize, i8)>> {
    if highs.len() != lows.len() {
        return Err(pyo3::exceptions::PyValueError::new_err("high/low length mismatch"));
    }
    let mut out = Vec::new();
    if highs.len() < 2 * k + 1 { return Ok(out); }
    for center in k..highs.len()-k {
        let hi = highs[center];
        let lo = lows[center];
        let mut max = f64::NEG_INFINITY;
        let mut min = f64::INFINITY;
        for i in center-k..=center+k {
            max = max.max(highs[i]);
            min = min.min(lows[i]);
        }
        if hi == max { out.push((center, 1)); }
        if lo == min { out.push((center, -1)); }
    }
    Ok(out)
}

#[pyfunction]
fn touch_track(low: Vec<f64>, high: Vec<f64>, close: Vec<f64>, prices: Vec<f64>,
               directions: Vec<i8>, atr: Vec<f64>) -> PyResult<Vec<(Vec<usize>, Option<usize>)>> {
    if low.len() != high.len() || low.len() != close.len() || low.len() != atr.len() || prices.len() != directions.len() {
        return Err(pyo3::exceptions::PyValueError::new_err("touch tracking input length mismatch"));
    }
    let mut output = Vec::with_capacity(prices.len());
    for (price, direction) in prices.iter().zip(directions.iter()) {
        let mut touches = Vec::new();
        let mut touching = false;
        let mut invalid = None;
        for i in 0..low.len() {
            let now = low[i] <= *price && *price <= high[i];
            if now && !touching { touches.push(i); }
            touching = now;
            if i32::from(*direction) < 0 && close[i] > *price + 0.25 * atr[i] ||
               i32::from(*direction) > 0 && close[i] < *price - 0.25 * atr[i] {
                invalid = Some(i);
                break;
            }
        }
        output.push((touches, invalid));
    }
    Ok(output)
}

#[pyfunction]
#[pyo3(signature = (rows_bytes, timestamps_bytes, jobs, job_size=None, second_rows_bytes=None, second_timestamps_bytes=None, return_stats=false))]
fn first_hit_batch(rows_bytes: Vec<u8>, timestamps_bytes: Vec<u8>, jobs: Vec<f64>, job_size: Option<usize>,
                   second_rows_bytes: Option<Vec<u8>>, second_timestamps_bytes: Option<Vec<u8>>,
                   return_stats: bool) -> PyResult<Vec<f64>> {
    if rows_bytes.len() % 8 != 0 || timestamps_bytes.len() % 8 != 0 {
        return Err(pyo3::exceptions::PyValueError::new_err("invalid label batch buffer length"));
    }
    let rows: Vec<f64> = rows_bytes.chunks_exact(8).map(|b| f64::from_le_bytes(b.try_into().unwrap())).collect();
    let timestamps: Vec<i64> = timestamps_bytes.chunks_exact(8).map(|b| i64::from_le_bytes(b.try_into().unwrap())).collect();
    let n = timestamps.len();
    if rows.len() != n * 8 {
        return Err(pyo3::exceptions::PyValueError::new_err("bar/timestamp length mismatch"));
    }
    let size = job_size.unwrap_or_else(|| if jobs.len() % 8 == 0 { 8 } else { 11 });
    if (size != 8 && size != 11) || jobs.len() % size != 0 {
        return Err(pyo3::exceptions::PyValueError::new_err("job size must be 8 or 11 and divide the job buffer"));
    }
    let mut bars = Vec::with_capacity(n);
    for row in rows.chunks_exact(8) {
        if row.iter().any(|value| !value.is_finite()) {
            return Err(pyo3::exceptions::PyValueError::new_err("bars must contain finite OHLC values"));
        }
        bars.push([row[0],row[1],row[2],row[3],row[4],row[5],row[6],row[7]]);
    }
    let second_rows: Vec<f64> = second_rows_bytes.unwrap_or_default().chunks_exact(8)
        .map(|b| f64::from_le_bytes(b.try_into().unwrap())).collect();
    let second_stamps: Vec<i64> = second_timestamps_bytes.unwrap_or_default().chunks_exact(8)
        .map(|b| i64::from_le_bytes(b.try_into().unwrap())).collect();
    if second_rows.len() != second_stamps.len() * 8 {
        return Err(pyo3::exceptions::PyValueError::new_err("second bar/timestamp length mismatch"));
    }
    let second_bars: Vec<[f64;8]> = second_rows.chunks_exact(8).map(|row|
        [row[0],row[1],row[2],row[3],row[4],row[5],row[6],row[7]]).collect();
    let seconds = if second_bars.is_empty() { None } else { Some((second_bars.as_slice(), second_stamps.as_slice())) };
    let output_width=if size==8 {5}else{9};
    let mut output = Vec::with_capacity(jobs.len() / size * (output_width + if return_stats {4}else{0}));
    for job in jobs.chunks_exact(size) {
        let signal=job[0] as usize; let side=job[1] as i8;
        let entry_price=job[2];let sl=job[3];let tp=if job[4].is_finite(){Some(job[4])}else{None};
        let delay=job[6].max(0.0) as usize;
        let finance=job[7];
        let (max_bars,deadline,limit,expiry,crypto)=if size==8 {
            (Some(job[5].max(0.0) as usize),None,None,None,false)
        } else {
            (None,if job[5].is_finite(){Some(job[5] as i64)}else{None},
             if job[8].is_finite(){Some(job[8])}else{None},
             if job[9].is_finite(){Some(job[9] as i64)}else{None},job[10]!=0.0)
        };
        let hit=simulate_one(&bars,&timestamps,signal,side,entry_price,sl,tp,delay,deadline,finance,limit,expiry,crypto,max_bars,seconds);
        if size==8 {
            output.extend([hit.outcome as f64,hit.exit_index as f64,hit.exit,hit.net_r,hit.gross_r]);
        } else {
            output.extend([hit.outcome as f64,hit.exit_index as f64,hit.fill,hit.exit,hit.net_r,hit.gross_r,
                           hit.rollovers as f64,hit.entry_index as f64,hit.planned_risk]);
        }
        if return_stats { output.extend(hit.stats.map(|value| value as f64)); }
    }
    Ok(output)
}

#[pymodule]
fn _msd_kernels(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(first_hit, m)?)?;
    m.add_function(wrap_pyfunction!(first_hit_with_stats, m)?)?;
    m.add_function(wrap_pyfunction!(pivots, m)?)?;
    m.add_function(wrap_pyfunction!(touch_track, m)?)?;
    m.add_function(wrap_pyfunction!(first_hit_batch, m)?)?;
    Ok(())
}
