mkdir -p api_reference
wget \
  --mirror \
  --convert-links \
  --adjust-extension \
  --page-requisites \
  --no-parent \
  -P api_reference \
  https://apinext.collegefootballdata.com/

pip install -r cfb_data/requirements.txt --no-cache-dir

pip install --upgrade setuptools

pre-commit install --install-hooks
