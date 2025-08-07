const { createApp, onMounted, onUnmounted, ref } = Vue;

createApp({
    setup() {
        let fetchInterval;

        // TODO: change apexchart date format based on this
        const MS = {
            minute: 60 * 1000,
            hour: 60 * 60 * 1000,
            day: 24 * 60 * 60 * 1000,
        };
        const now = () => { return new Date().getTime() }
        const filter_date_ranges = {
            _30min: now() - 30 * MS.minute,
            _60min: now() - 60 * MS.minute,
            _3h: now() - 3 * MS.hour,
            _6h: now() - 6 * MS.hour,
            _12h: now() - 12 * MS.hour,
            _24h: now() - 24 * MS.hour,
            _3days: now() - 3 * MS.day,
            _7days: now() - 7 * MS.day,
        };

        // TODO: this is ran once!
        const filter_date_min = filter_date_ranges._30min

        const http_status_code_colors = {
            "1XX": "#64748b",
            "2XX": "#10B981",
            "3XX": "#eab308",
            "4XX": "#f97316",
            "5XX": "#ef4444",
        }

        const requests_per_method_count = {
            GET: 0,
            POST: 0,
            PUT: 0,
            PATCH: 0,
            DELETE: 0,
            OPTION: 0,
        }

        const tableRows = ref(null)

        const current_cpu_usage = ref(0)
        const current_memory_usage = ref(0)
        const current_memory_used = ref(0)
        const current_memory_available = ref(0)
        const current_transmit_bytes = ref(0)
        const current_received_bytes = ref(0)

        const top_routes_total = ref(0)
        const top_routes = ref({})

        const top_slowest_routes = ref({})
        const top_error_prone_routes = ref({})

        // SYSTEM METRICS
        const cpu_chart_options = ref({
            chart: {
                type: "line",
                height: "85%",
                width: "97%",
                toolbar: {
                    show: false,
                },
                zoom: {
                    enabled: false,
                    allowMouseWheelZoom: false,
                },
                dropShadow: {
                    enabled: false,
                },
                yaxis: {
                    show: false,
                },
                animations: {
                    enabled: false,
                },
            },
            tooltip: {
                theme: 'dark',
                style: {
                    fontSize: '10px',
                }
            },
            legend: {
                show: false
            },
            dataLabels: {
                enabled: false,
            },
            stroke: {
                width: [2, 2],
                curve: "smooth",
            },
            grid: {
                borderColor: "#252525",
                strokeDashArray: 2,
                xaxis: {
                    lines: {
                        show: true,
                    },
                },
            },
            xaxis: {
                type: "datetime",
                axisBorder: {
                    show: false,
                },
                axisTicks: {
                    show: false,
                },
                labels: {
                    formatter: function (value) {
                        return new Date(value).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                        });
                    }
                },
                min: filter_date_min,
            },
            yaxis: {
                min: 0,
                max: 100,
                labels: {
                    formatter: function (val) {
                        return Math.round(val)
                    }
                }
            },
            series: [],
        });
        const memory_chart_options = ref({
            chart: {
                type: "line",
                height: "85%",
                width: "97%",
                toolbar: {
                    show: false,
                },
                zoom: {
                    enabled: false,
                    allowMouseWheelZoom: false,
                },
                dropShadow: {
                    enabled: false,
                },
                yaxis: {
                    show: false,
                },
                animations: {
                    enabled: false,
                },
            },
            tooltip: {
                theme: 'dark',
                style: {
                    fontSize: '10px',
                }
            },
            legend: {
                position: "top",
                horizontalAlign: "right",
                floating: true,
                offsetY: -25,
                offsetX: -5,
            },
            dataLabels: {
                enabled: false,
            },
            stroke: {
                width: [2, 2],
                curve: "smooth",
            },
            grid: {
                borderColor: "#252525",
                strokeDashArray: 2,
                xaxis: {
                    lines: {
                        show: true,
                    },
                },
            },
            xaxis: {
                type: "datetime",
                axisBorder: {
                    show: false,
                },
                axisTicks: {
                    show: false,
                },
                labels: {
                    formatter: (value) => {
                        return new Date(value).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                        });
                    },
                },
                min: filter_date_min,
            },
            yaxis: {
                min: 0,
                max: 100,
                labels: {
                    formatter: function (val) {
                        return Math.round(val)
                    }
                }
            },
            series: [],
        });
        const memory_used_and_available_chart_options = ref({
            chart: {
                type: "line",
                height: "83%",
                width: "97%",
                toolbar: {
                    show: false,
                },
                zoom: {
                    enabled: false,
                    allowMouseWheelZoom: false,
                },
                dropShadow: {
                    enabled: false,
                },
                yaxis: {
                    show: false,
                },
                animations: {
                    enabled: false,
                },
            },
            tooltip: {
                theme: 'dark',
                style: {
                    fontSize: '10px',
                }
            },
            legend: {
                show: false,
            },
            dataLabels: {
                enabled: false,
            },
            stroke: {
                width: [2, 2],
                curve: "smooth",
            },
            grid: {
                borderColor: "#252525",
                strokeDashArray: 2,
                xaxis: {
                    lines: {
                        show: true,
                    },
                },
            },
            colors: ["#10B981", "#085b3f"],
            xaxis: {
                type: "datetime",
                axisBorder: {
                    show: false,
                },
                axisTicks: {
                    show: false,
                },
                labels: {
                    formatter: (value) => {
                        return new Date(value).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                        });
                    },
                },
                min: filter_date_min,
            },
            yaxis: {
                labels: {
                    formatter: function (val) {
                        return Math.round(val)
                    }
                }
            },
            series: [],
        });
        const network_io_chart_options = ref({
            chart: {
                type: "line",
                height: "83%",
                width: "97%",
                toolbar: {
                    show: false,
                },
                zoom: {
                    enabled: false,
                    allowMouseWheelZoom: false,
                },
                dropShadow: {
                    enabled: false,
                },
                yaxis: {
                    show: false,
                },
                animations: {
                    enabled: false,
                },
            },
            tooltip: {
                theme: 'dark',
                style: {
                    fontSize: '10px',
                }
            },
            legend: {
                show: false,
            },
            dataLabels: {
                enabled: false,
            },
            stroke: {
                width: [2, 2],
                curve: "smooth",
            },
            grid: {
                borderColor: "#252525",
                strokeDashArray: 2,
                xaxis: {
                    lines: {
                        show: true,
                    },
                },
            },
            colors: ["#10B981", "#085b3f"],
            xaxis: {
                type: "datetime",
                axisBorder: {
                    show: false,
                },
                axisTicks: {
                    show: false,
                },
                labels: {
                    formatter: (value) => {
                        return new Date(value).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                        });
                    },
                },
                min: filter_date_min,
            },
            yaxis: {
                labels: {
                    formatter: function (val) {
                        return Math.round(val / (1024 * 1024))
                    }
                }
            },
            series: [],
        });

        // REQUEST METRICS
        const rpm_chart_options = ref({
            chart: {
                type: 'bar',
                height: "85%",
                width: "100%",
                toolbar: {
                    show: false,
                },
                zoom: {
                    enabled: false,
                    allowMouseWheelZoom: false,
                },
                stacked: true,
                animations: {
                    enabled: false
                },
            },
            tooltip: {
                theme: 'dark',
                style: {
                    fontSize: '10px',
                }
            },
            dataLabels: {
                enabled: false,
            },
            grid: {
                borderColor: "#252525",
                strokeDashArray: 2,
                xaxis: {
                    lines: {
                        show: true,
                    },
                },
            },
            plotOptions: {
                bar: {
                    horizontal: false,
                    borderRadius: 2,
                    borderRadiusApplication: 'end', // 'around', 'end'
                    borderRadiusWhenStacked: 'last', // 'all', 'last'
                    dataLabels: {
                        total: {
                            enabled: false,
                        }
                    }
                },
            },
            xaxis: {
                type: 'datetime',
                axisBorder: {
                    show: false,
                },
                axisTicks: {
                    show: false,
                },
                labels: {
                    formatter: (value) => {
                        return new Date(value).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                        });
                    },
                },
                min: filter_date_min,
            },
            legend: {
                show: false,
            },
            fill: {
                opacity: 1
            },
            series: [],
        });
        const read_write_per_minute_chart_options = ref({
            chart: {
                type: "line",
                height: "85%",
                width: "100%",
                toolbar: {
                    show: false,
                },
                zoom: {
                    enabled: false,
                    allowMouseWheelZoom: false,
                },
                dropShadow: {
                    enabled: false,
                },
                yaxis: {
                    show: false,
                },
                animations: {
                    enabled: false,
                },
            },
            tooltip: {
                theme: 'dark',
                style: {
                    fontSize: '10px',
                }
            },
            legend: {
                show: false,
            },
            dataLabels: {
                enabled: false,
            },
            stroke: {
                width: [2, 2],
                curve: "smooth",
            },
            grid: {
                borderColor: "#252525",
                strokeDashArray: 2,
                xaxis: {
                    lines: {
                        show: true,
                    },
                },
            },
            colors: ["#10B981", "#3D3F9C"],
            xaxis: {
                type: "datetime",
                axisBorder: {
                    show: false,
                },
                axisTicks: {
                    show: false,
                },
                labels: {
                    formatter: function (value) {
                        return new Date(value).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                        });
                    }
                },
                min: filter_date_min,
            },
            yaxis: {
                min: 0,
                labels: {
                    formatter: function (val) {
                        return Math.round(val)
                    }
                }
            },
            series: [],
        });
        const latency_per_route_chart_options = ref({
            chart: {
                type: "line",
                height: "85%",
                width: "100%",
                toolbar: {
                    show: false,
                },
                zoom: {
                    enabled: false,
                    allowMouseWheelZoom: false,
                },
                dropShadow: {
                    enabled: false,
                },
                yaxis: {
                    show: false,
                },
                animations: {
                    enabled: false,
                },
            },
            tooltip: {
                theme: 'dark',
                style: {
                    fontSize: '10px',
                },
                y: {
                    show: true,
                    formatter: (val) => formatTime(val, true)
                },
            },
            legend: {
                show: false,
            },
            dataLabels: {
                enabled: false,
            },
            stroke: {
                width: [2, 2],
                curve: "smooth",
            },
            grid: {
                borderColor: "#252525",
                strokeDashArray: 2,
                xaxis: {
                    lines: {
                        show: true,
                    },
                },
            },
            // colors: ["#10B981"],
            xaxis: {
                type: "datetime",
                axisBorder: {
                    show: false,
                },
                axisTicks: {
                    show: false,
                },
                labels: {
                    formatter: function (value) {
                        return new Date(value).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                        });
                    }
                },
                min: filter_date_min,
            },
            yaxis: {
                min: 0,
                labels: {
                    formatter: (val) => Math.round(formatTime(val, false))
                }
            },
            series: [],
        });
        const error_requests_chart_options = ref({
            chart: {
                type: 'bar',
                height: "85%",
                width: "100%",
                toolbar: {
                    show: false,
                },
                zoom: {
                    enabled: false,
                    allowMouseWheelZoom: false,
                },
                stacked: true,
                animations: {
                    enabled: false
                },
            },
            tooltip: {
                theme: 'dark',
                style: {
                    fontSize: '10px',
                }
            },
            dataLabels: {
                enabled: false,
            },
            grid: {
                borderColor: "#252525",
                strokeDashArray: 2,
                xaxis: {
                    lines: {
                        show: true,
                    },
                },
            },
            plotOptions: {
                bar: {
                    horizontal: false,
                    borderRadius: 2,
                    borderRadiusApplication: 'end', // 'around', 'end'
                    borderRadiusWhenStacked: 'last', // 'all', 'last'
                    dataLabels: {
                        total: {
                            enabled: false,
                        }
                    }
                },
            },
            xaxis: {
                type: 'datetime',
                axisBorder: {
                    show: false,
                },
                axisTicks: {
                    show: false,
                },
                labels: {
                    formatter: (value) => {
                        return new Date(value).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                        });
                    },
                },
                min: filter_date_min,
            },
            legend: {
                show: false,
            },
            fill: {
                opacity: 1
            },
            series: [],
        });

        // SYSTEM METRICS
        const cpu_chart = ref(null)
        const memory_chart = ref(null)
        const memory_used_and_available_chart = ref(null)
        const network_io_chart = ref(null)

        // REQUEST METRICS
        const rpm_chart = ref(null)
        const read_write_per_minute_chart = ref(null)
        const latency_per_route_chart = ref(null)

        // ERROR METRICS
        const error_requests_chart = ref(null)

        function formatTime(seconds, unit) {
            if (seconds >= 1) {
                return unit ? `${seconds.toFixed(3)} s` : seconds.toFixed(3)
            } else if (seconds >= 1e-3) {
                return unit ? `${(seconds * 1e3).toFixed(3)} ms` : (seconds * 1e3).toFixed(3)
            } else if (seconds >= 1e-6) {
                return unit ? `${(seconds * 1e6).toFixed(3)} µs` : (seconds * 1e6).toFixed(3)
            }
            return seconds
        }

        function renderCharts() {
            cpu_chart.value = new ApexCharts(document.querySelector("#cpu_chart"), cpu_chart_options.value);
            memory_chart.value = new ApexCharts(document.querySelector("#memory_chart"), memory_chart_options.value);
            memory_used_and_available_chart.value = new ApexCharts(document.querySelector("#memory_used_and_available_chart"), memory_used_and_available_chart_options.value);
            network_io_chart.value = new ApexCharts(document.querySelector("#network_io_chart"), network_io_chart_options.value);
            rpm_chart.value = new ApexCharts(document.querySelector("#request_per_minute_chart"), rpm_chart_options.value);
            read_write_per_minute_chart.value = new ApexCharts(document.querySelector("#read_write_per_minute_chart"), read_write_per_minute_chart_options.value);
            latency_per_route_chart.value = new ApexCharts(document.querySelector("#latency_per_route_chart"), latency_per_route_chart_options.value);
            error_requests_chart.value = new ApexCharts(document.querySelector("#error_requests_chart"), error_requests_chart_options.value);

            cpu_chart.value.render();
            memory_chart.value.render();
            memory_used_and_available_chart.value.render();
            network_io_chart.value.render();
            rpm_chart.value.render();
            read_write_per_minute_chart.value.render();
            latency_per_route_chart.value.render();
            error_requests_chart.value.render();
        }

        async function getData() {
            const tsFrom = Math.floor(Date.now() / 1000) - 60 * 60 // 60 mins ago
            const url = `/metrics/json?ts_from=${tsFrom}`
            try {
                const response = await fetch(url)
                if (!response.ok) {
                    console.log("problem getting data")
                }
                // timestamp is in seconds but js needs milis 
                const formatForChart = (data, key) => { return data.map(point => [point.timestamp * 1000, point[key]]) }

                const json_response = await response.json()

                cpu_chart.value.updateSeries([
                    {
                        name: "min",
                        color: "#0d9568",
                        data: formatForChart(json_response.system.cpu_percent, 'min')
                    },
                    {
                        name: "avg",
                        color: "#10B981",
                        data: formatForChart(json_response.system.cpu_percent, 'avg')
                    },
                    {
                        name: "max",
                        color: "#13dd9a",
                        data: formatForChart(json_response.system.cpu_percent, 'max')
                    }
                ])
                memory_chart.value.updateSeries([{
                    name: "avg",
                    color: "#10B981",
                    data: formatForChart(json_response.system.memory_percent, 'avg')
                }])
                memory_used_and_available_chart.value.updateSeries([
                    {
                        name: "Memory used (MiB)",
                        color: "#10B981",
                        data: formatForChart(json_response.system.memory_used_mb, 'avg')
                    },
                    {
                        name: "Memory available (MiB)",
                        color: "#085b3f",
                        data: formatForChart(json_response.system.memory_available_mb, 'avg')
                    }
                ])
                network_io_chart.value.updateSeries([
                    {
                        name: "Network bytes sent (Mbps)",
                        color: "#10B981",
                        data: formatForChart(json_response.system.network_io_sent, 'avg')
                    },
                    {
                        name: "Network bytes recieved (Mbps)",
                        color: "#085b3f",
                        data: formatForChart(json_response.system.network_io_recv, 'avg')
                    }
                ])

                read_write_per_minute_chart.value.updateSeries(
                    json_response.read_write.map(item => {
                        return {
                            name: item.name,
                            data: item.data.map(point => [point[0] * 1000, point[1]])
                        }
                    })
                )
                latency_per_route_chart.value.updateSeries(
                    json_response.latencies.map(item => {
                        return {
                            name: item.name,
                            data: item.data.map(point => [point[0] * 1000, point[1]])
                        }
                    })
                )
                rpm_chart.value.updateSeries(
                    json_response.status_code.map(item => {
                        return {
                            name: item.name,
                            color: http_status_code_colors[item.name],
                            data: item.data.map(point => [point[0] * 1000, point[1]])
                        }
                    })
                )

                error_requests_chart.value.updateSeries([
                    {
                        name: "4XX",
                        color: http_status_code_colors["4XX"],
                        data: json_response.status_code.find(item => item.name === "4XX").data.map(point => [point[0] * 1000, point[1]])
                    },
                    {
                        name: "5XX",
                        color: http_status_code_colors["5XX"],
                        data: json_response.status_code.find(item => item.name == "5XX")?.data.map(point => [point[0] * 1000, point[1]])
                    }
                ])

                tableRows.value = Object.entries(json_response.overview_table.rows).map(([route, data]) => ({
                    route,
                    ...data
                }))

                Object.entries(json_response.requests_per_method).forEach(([key, val]) => {
                    requests_per_method_count[key] = val
                });

                top_routes.value = json_response.top_routes
                top_routes_total.value = Object.values(json_response.top_routes).reduce((sum, val) => sum + val, 0)
                top_slowest_routes.value = json_response.top_slowest_routes
                top_error_prone_routes.value = json_response.top_error_prone_requests

                current_cpu_usage.value = parseInt(json_response.system.cpu_percent.slice(-1)[0]["avg"])
                current_memory_usage.value = parseInt(json_response.system.memory_percent.slice(-1)[0]["avg"])
                current_memory_used.value = parseInt(json_response.system.memory_used_mb.slice(-1)[0]["avg"])
                current_memory_available.value = parseInt(json_response.system.memory_available_mb.slice(-1)[0]["avg"])
                current_transmit_bytes.value = parseInt(json_response.system.network_io_sent.slice(-1)[0]["avg"] / (1024 * 1024))
                current_received_bytes.value = parseInt(json_response.system.network_io_recv.slice(-1)[0]["avg"] / (1024 * 1024))
            } catch (error) {
                console.log(error)
            }
        }

        onMounted(() => {
            renderCharts()
            getData()
            fetchInterval = setInterval(() => {
                getData()
            }, 10 * 1000)
        });

        onUnmounted(() => {
            clearInterval(fetchInterval);
            cpu_chart.value.destroy();
            memory_chart.value.destroy();
            memory_used_and_available_chart.value.destroy();
            network_io_chart.value.destroy();
            rpm_chart.value.destroy();
            read_write_per_minute_chart.value.destroy();
            latency_per_route_chart.value.destroy();
            error_requests_chart.value.destroy();
        })

        return {
            tableRows,
            current_cpu_usage,
            current_memory_usage,
            current_memory_used,
            current_memory_available,
            current_transmit_bytes,
            current_received_bytes,
            requests_per_method_count,
            top_routes,
            top_routes_total,
            top_slowest_routes,
            top_error_prone_routes,
            formatTime,
        }
    },
}).mount("#app");
