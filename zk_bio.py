from zk import ZK
from datetime import datetime, time


# ==============================
# BIOMETRIC DEVICE CONFIG
# ==============================

DEVICE_IP = "192.168.1.230"
DEVICE_PORT = 4370

OUTPUT_FILE = "biometric_logs.txt"


# ==============================
# DATE FILTER
# ==============================

START_DATE = datetime(2026, 9, 1)
END_DATE = datetime(2026, 9, 2, 23, 59, 59)


def capture_logs():

    zk = ZK(
        DEVICE_IP,
        port=DEVICE_PORT,
        timeout=10,
        password=0,
        force_udp=False,
        ommit_ping=False,
    )

    conn = None

    try:
        print(
            f"Connecting to biometric device: "
            f"{DEVICE_IP}:{DEVICE_PORT}"
        )

        conn = zk.connect()

        print("Connected successfully.")

        # Disable device while reading logs
        conn.disable_device()

        print("Reading attendance logs...")

        attendance_logs = conn.get_attendance()

        print(f"Total logs found in device: {len(attendance_logs)}")

        # ==============================
        # FILTER LOGS BY DATE
        # ==============================

        filtered_logs = []

        for log in attendance_logs:

            log_datetime = log.timestamp

            if START_DATE <= log_datetime <= END_DATE:
                filtered_logs.append(log)

        print(
            f"Logs from {START_DATE.date()} "
            f"to {END_DATE.date()}: {len(filtered_logs)}"
        )

        # ==============================
        # WRITE FILTERED LOGS TO TXT
        # ==============================

        with open(OUTPUT_FILE, "w", encoding="utf-8") as file:

            file.write(
                f"{'USER ID':<15}"
                f"{'DATETIME':<25}"
                f"{'PUNCH CODE':<15}\n"
            )

            file.write("-" * 55 + "\n")

            for log in filtered_logs:

                user_id = str(log.user_id)
                datetime_value = log.timestamp
                punch_code = str(log.punch)

                file.write(
                    f"{user_id:<15}"
                    f"{str(datetime_value):<25}"
                    f"{punch_code:<15}\n"
                )

        print(f"Logs successfully saved to: {OUTPUT_FILE}")

    except Exception as e:
        print("Error:", e)

    finally:

        if conn:
            try:
                conn.enable_device()
                conn.disconnect()
                print("Device disconnected.")
            except Exception:
                pass


if __name__ == "__main__":
    capture_logs()
