from __future__ import annotations


class FilterGraphBuilder:
    @staticmethod
    def preprocess_to_output(filter_chain: str, filter_output: str) -> str:
        """Conecta explícitamente la salida del preproceso al label [out]."""
        if not filter_chain.strip():
            return "[0:a]anull[out]"
        if not filter_output:
            return f"{filter_chain}[out]"
        return f"{filter_chain};[{filter_output}]anull[out]"

    @staticmethod
    def with_tail_filters(filter_chain: str, filter_output: str, tail_filters: list[str]) -> str:
        """Conecta preproceso -> filtros finales -> [out] de forma consistente."""
        if not filter_chain.strip():
            raise ValueError("filter_chain vacío en with_tail_filters")
        if not filter_output:
            raise ValueError("filter_output vacío en with_tail_filters")
        if not tail_filters:
            return FilterGraphBuilder.preprocess_to_output(filter_chain, filter_output)
        return f"{filter_chain};[{filter_output}]" + ",".join(tail_filters) + "[out]"
