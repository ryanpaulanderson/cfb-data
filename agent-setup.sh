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

pre-commit install

pre-commit run --all-files # ensure dependencies are downloaded before offline access is cut
