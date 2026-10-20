"""Optional offline, review-only OCR for scanned PDF pages.

No network calls and no automatic updates to customer contracts. Tesseract is
not a handwriting recognition guarantee. Run a pilot and always check sources.
"""
from __future__ import annotations
import os,re,shutil,subprocess,tempfile,time
from pathlib import Path
import fitz

class LocalOCRError(Exception): pass

KEYWORDS=re.compile(r'\b(?:invoice|account|customer|contract|description|warranty|expiry|equipment|quantity|serial|pulsefitness)\b',re.I)

def available():
    return bool(shutil.which('tesseract') or (os.environ.get('PULSE_TESSERACT_PATH') and Path(os.environ['PULSE_TESSERACT_PATH']).is_file()))

def _score(text):
    return len(KEYWORDS.findall(text))*8 + len(re.findall(r'\b[A-Za-z]{4,}\b',text))

def _ocr(page,rotation=0,timeout=24):
    """Pass a rendered single page to Tesseract (never run a shell command)."""
    pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5).prerotate(rotation),colorspace=fitz.csGRAY,alpha=False)
    if pix.width * pix.height>9_000_000:
        raise LocalOCRError('This PDF page is too large for safe local OCR')
    binary=os.environ.get('PULSE_TESSERACT_PATH') or shutil.which('tesseract')
    if not binary:raise LocalOCRError('Tesseract was not found on this computer')
    with tempfile.NamedTemporaryFile(suffix='.png',delete=False) as tmp:
        path=tmp.name
    try:
        pix.save(path)
        run=subprocess.run([binary,path,'stdout','-l','eng','--psm','3'],
           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
        if run.returncode not in (0,):return ''
        return run.stdout.strip()[:100_000]
    except subprocess.TimeoutExpired:raise LocalOCRError('OCR timed out on this page')
    finally:
        Path(path).unlink(missing_ok=True)

def read_local_scanned_pdf(pdf:bytes,pages_to_read:list[int]):
    """Return pages with candidate text + per-page warnings, not verified facts.

    A poor-quality page may be upside down; a second rotation is attempted only
    if text quality is poor. Unreadable pages remain visibly unprocessed.
    """
    if not available():raise LocalOCRError('Install Tesseract OCR to enable local scanned-document reading')
    results=[];warnings=[]
    with fitz.open(stream=pdf,filetype='pdf') as doc:
        if len(doc)>75:raise LocalOCRError('PDF is too long for the local pilot; split it into batches of 75 pages')
        for page_number in sorted(set(pages_to_read))[:35]:
            if page_number<1 or page_number>len(doc):continue
            page=doc[page_number-1]
            try:
                text=_ocr(page)
                rotation=0
                if len(KEYWORDS.findall(text))<2:
                    alternate=_ocr(page,180)
                    if len(KEYWORDS.findall(alternate))>len(KEYWORDS.findall(text)) or _score(alternate)>_score(text)*1.35:
                        text=alternate;rotation=180
                if text.strip():
                    results.append({'page':page_number,'text':text,'source':'Tesseract offline OCR (unverified)', 'rotation':rotation})
                else:warnings.append(f'Page {page_number}: no readable text detected')
            except Exception as e:
                warnings.append(f'Page {page_number}: {str(e)[:100]}')
    return results,warnings
