package com.jarvis.newapp;

import android.Manifest;
import android.app.Activity;
import android.os.Bundle;
import android.content.*;
import android.content.pm.PackageManager;
import android.speech.RecognizerIntent;
import android.speech.tts.TextToSpeech;
import android.graphics.Color;
import android.view.Gravity;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;

public class MainActivity extends Activity {
    private TextToSpeech tts;
    private TextView status;
    private EditText input;
    private static final int REQ=7;
    private final ExecutorService net=Executors.newSingleThreadExecutor();
    private android.content.SharedPreferences prefs;

    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        prefs=getSharedPreferences("jarvis",MODE_PRIVATE);
        buildUi();
        tts=new TextToSpeech(this,s->{if(s==TextToSpeech.SUCCESS)tts.setLanguage(new Locale("ru","RU"));});
        if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},REQ);
    }

    private TextView tv(String s,int sp){
        TextView v=new TextView(this); v.setText(s); v.setTextColor(Color.WHITE); v.setTextSize(sp); v.setGravity(Gravity.CENTER); return v;
    }

    private void buildUi(){
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(28,24,28,20); root.setBackgroundColor(Color.rgb(5,8,13));
        TextView title=tv("JARVIS",30); title.setTextColor(Color.rgb(99,230,255));
        root.addView(title,new LinearLayout.LayoutParams(-1,62));
        TextView sub=tv("НОВАЯ СИСТЕМА",12); sub.setTextColor(Color.rgb(145,160,175));
        root.addView(sub,new LinearLayout.LayoutParams(-1,30));
        Space top=new Space(this); root.addView(top,new LinearLayout.LayoutParams(1,20));
        TextView orb=tv("J\nA\nR\nV\nI\nS",18); orb.setTextColor(Color.rgb(99,230,255));
        orb.setBackgroundResource(com.jarvis.newapp.R.drawable.orb);
        LinearLayout.LayoutParams op=new LinearLayout.LayoutParams(240,240); op.gravity=Gravity.CENTER; root.addView(orb,op);
        status=tv("ГОТОВ. СКАЖИТЕ «JARVIS»",14); status.setTextColor(Color.rgb(170,185,200));
        root.addView(status,new LinearLayout.LayoutParams(-1,64));
        input=new EditText(this); input.setHint("Введите запрос…"); input.setHintTextColor(Color.rgb(100,115,130));
        input.setTextColor(Color.WHITE); input.setSingleLine(true);
        root.addView(input,new LinearLayout.LayoutParams(-1,58));
        LinearLayout row=new LinearLayout(this); row.setGravity(Gravity.CENTER);
        Button mic=new Button(this); mic.setText("МИКРОФОН");
        Button send=new Button(this); send.setText("ОТПРАВИТЬ");
        row.addView(mic,new LinearLayout.LayoutParams(0,58,1)); row.addView(send,new LinearLayout.LayoutParams(0,58,1));
        root.addView(row);
        Button settings=new Button(this); settings.setText("НАСТРОЙКИ МОЗГА"); root.addView(settings,new LinearLayout.LayoutParams(-1,54));
        send.setOnClickListener(v->answer(input.getText().toString()));
        mic.setOnClickListener(v->listen());
        settings.setOnClickListener(v->brainSettings());
        setContentView(root);
    }

    private void brainSettings(){
        LinearLayout box=new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(32,8,32,0);
        EditText url=new EditText(this); url.setHint("URL API"); url.setText(prefs.getString("url","https://openrouter.ai/api/v1/chat/completions"));
        EditText model=new EditText(this); model.setHint("Модель"); model.setText(prefs.getString("model","openai/gpt-4o-mini"));
        EditText key=new EditText(this); key.setHint("API ключ"); key.setInputType(0x00000081); key.setText(prefs.getString("key",""));
        box.addView(url); box.addView(model); box.addView(key);
        new AlertDialog.Builder(this).setTitle("МОЗГ JARVIS").setView(box)
            .setPositiveButton("СОХРАНИТЬ",(d,w)->{
                prefs.edit().putString("url",url.getText().toString().trim())
                    .putString("model",model.getText().toString().trim())
                    .putString("key",key.getText().toString().trim()).apply();
                status.setText("НАСТРОЙКИ МОЗГА СОХРАНЕНЫ");
            }).setNegativeButton("ОТМЕНА",null).show();
    }

    private void listen(){
        try{
            Intent i=new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE,"ru-RU");
            i.putExtra(RecognizerIntent.EXTRA_PROMPT,"Слушаю…");
            startActivityForResult(i,99); status.setText("СЛУШАЮ…");
        }catch(Exception e){status.setText("ГОЛОСОВОЙ ВВОД НЕДОСТУПЕН");}
    }

    @Override protected void onActivityResult(int r,int c,Intent d){
        super.onActivityResult(r,c,d);
        if(r==99&&c==RESULT_OK&&d!=null){
            ArrayList<String>a=d.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
            if(a!=null&&!a.isEmpty()){input.setText(a.get(0)); answer(a.get(0));}
        }
    }

    private void answer(String q){
        if(q==null||q.trim().isEmpty())return;
        final String prompt=q.trim(); status.setText("ОБРАБОТКА…");
        net.execute(()->{
            try{
                String key=prefs.getString("key","").trim();
                String url=prefs.getString("url","https://openrouter.ai/api/v1/chat/completions").trim();
                String model=prefs.getString("model","openai/gpt-4o-mini").trim();
                if(key.isEmpty()){showResult("НЕТ API КЛЮЧА. ОТКРОЙТЕ «НАСТРОЙКИ МОЗГА».",false);return;}
                JSONObject body=new JSONObject();
                body.put("model",model);
                JSONArray messages=new JSONArray();
                messages.put(new JSONObject().put("role","system").put("content","Ты JARVIS. Отвечай по-русски, кратко и по делу."));
                messages.put(new JSONObject().put("role","user").put("content",prompt));
                body.put("messages",messages);
                HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();
                c.setRequestMethod("POST"); c.setConnectTimeout(15000); c.setReadTimeout(30000);
                c.setRequestProperty("Content-Type","application/json");
                c.setRequestProperty("Authorization","Bearer "+key);
                c.setDoOutput(true);
                try(OutputStream os=c.getOutputStream()){os.write(body.toString().getBytes("UTF-8"));}
                int code=c.getResponseCode();
                InputStream is=code>=200&&code<300?c.getInputStream():c.getErrorStream();
                String resp=readAll(is);
                c.disconnect();
                if(code<200||code>=300){showResult("ОШИБКА API "+code+": "+shortError(resp),false);return;}
                JSONObject out=new JSONObject(resp);
                String answer=out.getJSONArray("choices").getJSONObject(0).getJSONObject("message").getString("content").trim();
                showResult(answer,true);
            }catch(Exception e){showResult("ОШИБКА СОЕДИНЕНИЯ: "+e.getMessage(),false);}
        });
    }

    private String readAll(InputStream in)throws Exception{
        if(in==null)return "";
        BufferedReader r=new BufferedReader(new InputStreamReader(in,"UTF-8")); StringBuilder s=new StringBuilder(); String line;
        while((line=r.readLine())!=null)s.append(line); return s.toString();
    }

    private String shortError(String s){
        try{JSONObject o=new JSONObject(s); if(o.has("error"))return o.getJSONObject("error").optString("message",s);}catch(Exception ignored){}
        return s.length()>300?s.substring(0,300):s;
    }

    private void showResult(String text,boolean speak){
        runOnUiThread(()->{status.setText(text); if(speak&&tts!=null)tts.speak(text,TextToSpeech.QUEUE_FLUSH,null,"jarvis");});
    }

    @Override protected void onDestroy(){net.shutdownNow(); if(tts!=null)tts.shutdown(); super.onDestroy();}
}
