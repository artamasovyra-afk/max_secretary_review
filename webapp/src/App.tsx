import { ConfigProvider } from "antd";
import ruRU from "antd/locale/ru_RU";
import dayjs from "dayjs";
import updateLocale from "dayjs/plugin/updateLocale";
import "dayjs/locale/ru";
import { RouterProvider } from "react-router-dom";
import { router } from "./routes";

dayjs.extend(updateLocale);
dayjs.locale("ru");
dayjs.updateLocale("ru", {
  weekStart: 1,
});

const sundayIndexedShortWeekDays = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];

const appLocale = {
  ...ruRU,
  Calendar: {
    ...ruRU.Calendar,
    lang: {
      ...ruRU.Calendar?.lang,
      dateFormat: "DD.MM.YYYY",
      dateTimeFormat: "DD.MM.YYYY HH:mm:ss",
      locale: "ru",
      now: "Сейчас",
      ok: "OK",
      shortWeekDays: sundayIndexedShortWeekDays,
      today: "Сегодня",
      weekStart: 1,
    },
  },
  DatePicker: {
    ...ruRU.DatePicker,
    lang: {
      ...ruRU.DatePicker?.lang,
      dateFormat: "DD.MM.YYYY",
      dateTimeFormat: "DD.MM.YYYY HH:mm:ss",
      locale: "ru",
      now: "Сейчас",
      ok: "OK",
      shortWeekDays: sundayIndexedShortWeekDays,
      today: "Сегодня",
      weekStart: 1,
    },
  },
} as typeof ruRU;

export function App() {
  return (
    <ConfigProvider
      locale={appLocale}
      theme={{
        token: {
          borderRadius: 6,
          colorPrimary: "#1677ff",
          fontFamily:
            "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif",
        },
      }}
    >
      <RouterProvider router={router} />
    </ConfigProvider>
  );
}
