# Modelos que vão no pacote do Ipê

- `densidade_nyu.onnx` — rede de densidade mamária (BI-RADS a–d) de Wu, Geras, Shen, Su, Kim, Kim, Wolfson, Moy e
  Cho, *Breast density classification with deep convolutional neural networks*, ICASSP 2018
  (https://github.com/nyukat/breast_density_classifier), licença **BSD 2-Clause**. Os pesos originais (PyTorch)
  foram convertidos para ONNX sem alteração; na imagem de exemplo do repositório original, a saída bate com a do
  PyTorch até 3 × 10⁻⁸. SHA-256: `acc6500272a6b81152066d8c71afd3e521bfbc749fc54c2f456b12b36fb96ddb`.
- `calc_vascular_scunet.onnx` — calcificações vasculares da mama (calcificação arterial), SCU-Net de Guo, O'Neill, Vey,
  Yang, Kim, Ghassemi, Pan, Gichoya, Trivedi e Banerjee, *SCU-Net: A deep learning method for segmentation and
  quantification of breast arterial calcifications on mammograms*, Med Phys 2021;48:5851–61
  (https://github.com/Emory-HITI/BAC_segmentation), licença **MIT** (Copyright (c) 2021 Xiaoyuan Guo; texto em `LICENSE-SCU-Net.txt`). Peso
  `SCU_Net_512_512_best_BCE_pos_all.pt` convertido para ONNX sem alteração (opset 17; diferença para o PyTorch
  ≤ 1,1 × 10⁻⁵ numa entrada aleatória). Saída em logit (o Ipê aplica a sigmoide). SHA-256:
  `8aa966780481298eee85a8db69215eb195523ac9aa79fdda1515c12039259e0a`.

Os outros modelos de IA (TotalSegmentator, MedSAM2, SynthSeg…) não vão aqui: são baixados à parte, pela instalação
das IAs, porque são grandes ou têm licença que não permite redistribuir.
