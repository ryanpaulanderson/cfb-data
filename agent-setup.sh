mkdir -p api_reference
wget \
  --mirror \
  --convert-links \
  --adjust-extension \
  --page-requisites \
  --no-parent \
  -P api_reference \
  https://apinext.collegefootballdata.com/
