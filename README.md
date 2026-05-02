# AudioMancer

AudioMancer is a desktop audiobook production application distributed here as a packaged Windows executable release.

## Windows Downloads

AudioMancer requires the companion VoiceWeaver runtime for local voice generation.

Download from the current GitHub Release:

- [AudioMancer_Windows_x64.zip](https://github.com/DDP-Engineering/2026_AudioMancer/releases/latest/download/AudioMancer_Windows_x64.zip)
- [SHA256SUMS.txt](https://github.com/DDP-Engineering/2026_AudioMancer/releases/latest/download/SHA256SUMS.txt)
- `VoiceWeaver-v1.2.2-windows-x64-cuda-models-3.zip.part001` through `VoiceWeaver-v1.2.2-windows-x64-cuda-models-3.zip.part010`

The VoiceWeaver archive is split into 10 release assets because the complete Windows package is larger than a single GitHub release asset.

## Install

1. Download `AudioMancer_Windows_x64.zip`.
2. Download all 10 VoiceWeaver `.partNNN` files into the same folder.
3. Reassemble the VoiceWeaver ZIP from the parts.
4. Verify SHA256 hashes with `SHA256SUMS.txt`.
5. Extract both ZIP archives before starting the applications.
6. Start AudioMancer with `AudioMancer.exe` or `Start-AudioMancer.cmd`.

## Reassemble VoiceWeaver On Windows

Run this from the folder containing all 10 VoiceWeaver parts:

```powershell
$parts = Get-ChildItem "VoiceWeaver-v1.2.2-windows-x64-cuda-models-3.zip.part*" | Sort-Object Name
$out = [IO.File]::Create("VoiceWeaver-v1.2.2-windows-x64-cuda-models-3.zip")
foreach ($part in $parts) {
    $in = [IO.File]::OpenRead($part.FullName)
    $in.CopyTo($out)
    $in.Dispose()
}
$out.Dispose()
Get-FileHash -Algorithm SHA256 .\VoiceWeaver-v1.2.2-windows-x64-cuda-models-3.zip
```

Expected reassembled VoiceWeaver ZIP SHA256:

```text
e957082578d5f844b98b1234fb9e1f69d48fec11f80d1acdd6b65432dd2d90b9
```

Expected AudioMancer ZIP SHA256:

```text
337b5fac0a26f502cf9bacc15cc51cbf874cd3d0ec17fbfd5e781e61ac9335e6
```

## Distribution Scope

This public repository is used for executable release delivery and the download webpage. It does not host the application source code.

## License

AudioMancer and VoiceWeaver are distributed under the license files included in each release archive.
