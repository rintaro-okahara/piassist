# Sibelius vector-PDF fixtures

Sibeliusが直接書き出したベクターPDFを、同じ公開データセットに含まれるMusicXMLと照合する回帰corpusです。PDF内の譜面フォント、文字origin、五線・小節線、音部記号、音符、臨時記号を検証します。

## 収録サンプル

- `aura_lee/`: 1ページ、単旋律lead sheet、4 systems、50音
- `beale_street_blues/`: 2ページ、反復・volta・triplet・tie/slurを含むlead sheet、149音
- `beautiful_ohio/`: 2ページ、2-part / 2-staff ensemble、127音
- `beethoven_op27_no2_i/`: 3ページ、treble/bassのpiano grand staff、69小節、PDF上1181 notehead glyphs

先頭3件はThe Public Domain Song Anthology v1.1（CC0-1.0）、BeethovenはBeethoven Piano Sonata Dataset v2（CC BY 3.0）から取得しました。出典・固定version・上流ファイル名・URL・checksum・Sibelius元ファイルの所在は`manifest.json`、ライセンスと帰属表示は`NOTICE.md`に記録しています。`.sib`自体はfixtureへ複製していません。

## 検証方法

PDSAの3件は、PDFから得た譜面順の全音符について、MusicXMLの音名・octave・実効臨時記号と照合します。複数partの`beautiful_ohio`は上下staffを各partへ対応させて比較します。

Beethovenは複数voice・和音を含むため、MusicXMLのsystem breakとstaff番号でPDFの各visual staffを対応付け、各system/staffの全音高multisetを比較します。MusicXMLは1182 note要素、PDFは1181 notehead glyphsです。差の1件はm15 beat 1 staff 1のB3で、2 voiceが同じ位置・同じ音高のnoteheadを共有するSibeliusの出力です。この1件だけをoracle側でcollapseします。

Sibeliusのtie/slurは同じ曲線をstroke pathとfill+stroke pathとして重ねて出力します。`fs`形式のtie受け入れ自体はunit testと実PDFで検証しますが、このcorpusではMusicXMLのtie件数との完全一致を合格条件にしていません。system/pageをまたぐtieと同音高slurの識別は別の改善対象です。

## 再取得

PDSAの各PDF/MusicXMLは`manifest.json`のdatafile URLから個別に再取得できます。BPSDのファイルは固定Zenodo recordのarchive memberです。再取得後はmanifestのMD5とSHA-256の両方を確認してください。
