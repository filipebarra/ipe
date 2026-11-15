# Modelos que vão no pacote do Ipê

- `densidade_nyu.onnx` — rede de densidade mamária (BI-RADS a–d) de Wu, Geras, Shen, Su, Kim, Kim, Wolfson, Moy e
  Cho, *Breast density classification with deep convolutional neural networks*, ICASSP 2018
  (https://github.com/nyukat/breast_density_classifier), licença **BSD 2-Clause**. Os pesos originais (PyTorch)
  foram convertidos para ONNX sem alteração; na imagem de exemplo do repositório original, a saída bate com a do
  PyTorch até 3 × 10⁻⁸. SHA-256: `acc6500272a6b81152066d8c71afd3e521bfbc749fc54c2f456b12b36fb96ddb`.

Os outros modelos de IA (TotalSegmentator, MedSAM2, SynthSeg…) não vão aqui: são baixados à parte, pela instalação
das IAs, porque são grandes ou têm licença que não permite redistribuir.
