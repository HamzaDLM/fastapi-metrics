from dataclasses import dataclass, field


@dataclass
class Config:
    ui_pin: int | None = None
    ignored_routes: list[str] = field(default_factory=list)
    enable_dashboard_ui: bool = True
    custom_path: str = "/metrics"
