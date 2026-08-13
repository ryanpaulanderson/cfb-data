# Rankings API

`client.rankings.list` implements historical poll rankings. `year` is required;
optional CFP `latest` and `final` snapshot selectors require `poll="cfp"` and
cannot both be true.

One frame row represents a season type and poll week. Its `polls` column keeps
the returned poll snapshots and ranked teams nested, preserving upstream order
without flattening distinct poll grains.
