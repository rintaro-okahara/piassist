# Third-party fixture notice

PiassistのソースコードとテストコードはAGPL-3.0-onlyですが、このディレクトリ内の第三者提供PDFとMusicXMLには以下のライセンスが個別に適用されます。

## The Public Domain Song Anthology v1.1

- Dataset: *The Public Domain Song Anthology*
- Authors: David Berger and Chuck Israels
- DOI: https://doi.org/10.18130/V3/C4RD06
- Released: 2023-09-22
- License: [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/)
- Included unchanged: `aura_lee/`, `beale_street_blues/`, `beautiful_ohio/`の`input.pdf`と`oracle.musicxml`
- Local changes: 内容は変更せず、fixture用の安定したファイル名へ変更

## Beethoven Piano Sonata Dataset v2

- Dataset: *BPSD: A Coherent Multi-Version Dataset for Analyzing the First Movements of Beethoven's Piano Sonatas*
- Authors: Johannes Zeitler, Christof Weiß, Vlora Arifi-Müller, and Meinard Müller
- DOI: https://doi.org/10.5281/zenodo.12783403
- Released: 2024-07-19
- License: [Creative Commons Attribution 3.0 Unported](https://creativecommons.org/licenses/by/3.0/)
- Included unchanged: `beethoven_op27_no2_i/input.pdf` and `beethoven_op27_no2_i/oracle.musicxml`
- Local changes: archiveから対象ファイルを抽出し、fixture用の安定したファイル名へ変更。内容の変更なし

正確な上流ファイル名、固定archive/datafile URL、MD5、SHA-256、および対応する`.sib`の所在は`manifest.json`に記録しています。上流の作者・データセット提供者によるPiassistの推奨や保証を示すものではありません。
