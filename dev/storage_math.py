# 16594560 bytes for a 3840x2160 16-bit FITS + header
w,h,bpp = 3840,2160,2
raw = w*h*bpp
fits_size = 16594560
print(f"raw 16-bit data: {raw/1e6:.2f} MB")
print(f"FITS on disk   : {fits_size/1e6:.2f} MB  (header overhead {(fits_size-raw)/1024:.0f} KB)")
free_mb = 94071
print(f"\nfree on scope  : {free_mb} MB")
print(f"max subs       : {free_mb*1e6//fits_size:,} frames")
print(f"at 10s/frame   : {free_mb*1e6/fits_size*10/3600:.1f} hours")
print(f"at 20s/frame   : {free_mb*1e6/fits_size*20/3600:.1f} hours")
print(f"\nOur plan ~7.2h effective ->")
for exp in (10,20):
    n = 7.2*3600/exp
    print(f"  {exp}s: {n:.0f} frames = {n*fits_size/1e9:.1f} GB")
