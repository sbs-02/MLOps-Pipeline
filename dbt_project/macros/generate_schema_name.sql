-- Override dbt's default schema naming so a model with `+schema: stg` lands in
-- the `stg` schema of the target database instead of `<target_schema>_stg`.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
