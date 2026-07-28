if (.resource_changes | type) != "array" then
  error("restore plan resource_changes must be an array")
elif (.output_changes | type) != "object" then
  error("restore plan output_changes must be an object")
else
  ([
    .resource_changes[]
    | select(.change.actions != ["no-op"])
  ] | length)
  + ([
    .output_changes[]
    | select(.actions != ["no-op"])
  ] | length)
end
