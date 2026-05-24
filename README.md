# AudioMancer

AudioMancer is a Windows desktop app for book translation and audiobook preparation.

It can help you:

- import a book and extract the text
- clean and split long text into workable pieces
- translate a book into another language
- find characters and prepare narrator or character voices
- create speech blocks for audiobook production
- generate local voice audio through VoiceWeaver
- assemble final WAV audiobook files

AI help is optional. You can use AI for cleanup, chunking, translation, character discovery, and speech blocks, then review and edit the result. You can also do the same work manually.

## Downloads

Use the current GitHub Release page for both AudioMancer and the VoiceWeaver runtime package:

- [AudioMancer v1.3.0 Windows release](https://github.com/DDP-Engineering/2026_AudioMancer/releases/tag/v1.3.0)

The release page includes:

- `AudioMancer_Windows_x64.zip`
- `SHA256SUMS.txt`
- VoiceWeaver runtime package links and checksum information

## Install AudioMancer

1. Download `AudioMancer_Windows_x64.zip` from the v1.3.0 release page.
2. Extract it to a normal folder, for example `C:\AudioMancer`.
3. Start AudioMancer with `AudioMancer.exe` or `Start-AudioMancer.cmd`.

## Install VoiceWeaver

1. Open the [AudioMancer v1.3.0 release page](https://github.com/DDP-Engineering/2026_AudioMancer/releases/tag/v1.3.0).
2. Download the VoiceWeaver runtime package parts linked in the VoiceWeaver section.
3. Put all parts in one folder.
4. Reassemble the VoiceWeaver ZIP with PowerShell.
5. Extract the VoiceWeaver ZIP to a normal folder, for example `C:\VoiceWeaver`.
6. Start VoiceWeaver with its Windows start file.
7. Check that the local health address works: `http://127.0.0.1:8059/v1/health`.

## Reassemble VoiceWeaver On Windows

Run this from the folder containing all VoiceWeaver parts:

```powershell
$outputZip = "VoiceWeaver-v1.5.0-windows-x64-cuda.zip"
$parts = Get-ChildItem "$outputZip.part*" | Sort-Object Name
$out = [IO.File]::Create($outputZip)
foreach ($part in $parts) {
    $in = [IO.File]::OpenRead($part.FullName)
    $in.CopyTo($out)
    $in.Dispose()
}
$out.Dispose()
Get-FileHash -Algorithm SHA256 $outputZip
```

## Connect AudioMancer To VoiceWeaver

1. Start VoiceWeaver first.
2. Start AudioMancer.
3. Open `TTS Settings`.
4. Set `Base URL` to `http://127.0.0.1:8059`.
5. Leave `API Key` empty for normal local use.
6. Press `Test Connection`.
7. Save the TTS settings.

## Distribution Scope

This public repository is used for executable release delivery and the download webpage. It does not host the application source code.

## License

AudioMancer and VoiceWeaver are distributed under the license files included in each release archive.