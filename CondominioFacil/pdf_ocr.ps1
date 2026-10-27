$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfPageRenderOptions, Windows.Data.Pdf, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null
$asOperation = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
$asAction = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
} | Select-Object -First 1
function Await-Operation($operation, [Type] $resultType) {
    $task = $asOperation.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.GetAwaiter().GetResult()
}
function Await-Action($operation) {
    $task = $asAction.Invoke($null, @($operation))
    $task.GetAwaiter().GetResult()
}
$language = New-Object Windows.Globalization.Language('pt-BR')
$engine = $null
if ([Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($language)) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
}
if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($null -eq $engine) { throw 'Nenhum idioma de OCR esta disponivel no Windows. Preencha os campos manualmente.' }
$file = Await-Operation ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:CONDOMINIO_PDF_PATH)) ([Windows.Storage.StorageFile])
$pdf = Await-Operation ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
if ($pdf.PageCount -gt 30) { throw 'O PDF excede o limite de 30 paginas.' }
$texts = @()
for ($i=0; $i -lt $pdf.PageCount; $i++) {
    $page = $pdf.GetPage($i)
    $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    try {
        $options = New-Object Windows.Data.Pdf.PdfPageRenderOptions
        $scale = [Math]::Min(1800.0 / $page.Size.Width, ([Windows.Media.Ocr.OcrEngine]::MaxImageDimension - 1.0) / [Math]::Max($page.Size.Width, $page.Size.Height))
        $options.DestinationWidth = [uint32][Math]::Floor($page.Size.Width * $scale)
        $options.DestinationHeight = [uint32][Math]::Floor($page.Size.Height * $scale)
        Await-Action ($page.RenderToStreamAsync($stream, $options))
        $stream.Seek(0)
        $decoder = Await-Operation ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await-Operation ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $result = Await-Operation ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            $texts += (($result.Lines | ForEach-Object { $_.Text }) -join "`n")
        } finally { $bitmap.Dispose() }
    } finally { $stream.Dispose(); $page.Dispose() }
}
@{pages=$texts; language=$engine.RecognizerLanguage.LanguageTag} | ConvertTo-Json -Compress -Depth 4
