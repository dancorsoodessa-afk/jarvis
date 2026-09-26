package com.jarvis.newapp;

import android.Manifest;
import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.speech.RecognizerIntent;
import android.speech.tts.TextToSpeech;
import android.graphics.Color;
import android.view.Gravity;
import android.view.View;
import android.widget.*;
import java.util.*;

public class MainActivity extends Activity {
    private TextToSpeech tts; private TextView status; private EditText input; private static final int REQ=7;
    @Override public void onCreate(Bundle b){ super.onCreate(b); buildUi();
        tts=new TextToSpeech(this, s -> { if(s==TextToSpeech.SUCCESS) tts.setLanguage(new Locale("ru","RU")); });
        if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED) requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ);
    }
    private TextView tv(String s,int sp){ TextView v=new TextView(this); v.setText(s); v.setTextColor(Color.WHITE); v.setTextSize(sp); v.setGravity(Gravity.CENTER); return v; }
    private void buildUi(){
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(28,32,28,24); root.setBackgroundColor(Color.rgb(5,8,13));
        TextView title=tv("JARVIS",30); title.setTextColor(Color.rgb(99,230,255)); root.addView(title,new LinearLayout.LayoutParams(-1,70));
        TextView sub=tv("НОВАЯ СИСТЕМА",12); sub.setTextColor(Color.rgb(145,160,175)); root.addView(sub,new LinearLayout.LayoutParams(-1,35));
        Space top=new Space(this); root.addView(top,new LinearLayout.LayoutParams(1,35));
        TextView orb=tv("J\nA\nR\nV\nI\nS",18); orb.setTextColor(Color.rgb(99,230,255)); orb.setBackgroundResource(com.jarvis.newapp.R.drawable.orb); LinearLayout.LayoutParams op=new LinearLayout.LayoutParams(260,260); op.gravity=Gravity.CENTER; root.addView(orb,op);
        status=tv("ГОТОВ. СКАЖИТЕ «JARVIS»",14); status.setTextColor(Color.rgb(170,185,200)); root.addView(status,new LinearLayout.LayoutParams(-1,70));
        input=new EditText(this); input.setHint("Введите запрос…"); input.setHintTextColor(Color.rgb(100,115,130)); input.setTextColor(Color.WHITE); input.setSingleLine(true); root.addView(input,new LinearLayout.LayoutParams(-1,60));
        LinearLayout row=new LinearLayout(this); row.setGravity(Gravity.CENTER); Button mic=new Button(this); mic.setText("МИКРОФОН"); Button send=new Button(this); send.setText("ОТПРАВИТЬ"); row.addView(mic,new LinearLayout.LayoutParams(0,60,1)); row.addView(send,new LinearLayout.LayoutParams(0,60,1)); root.addView(row);
        send.setOnClickListener(v->answer(input.getText().toString())); mic.setOnClickListener(v->listen()); setContentView(root);
    }
    private void listen(){ try{ Intent i=new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH); i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ru-RU"); i.putExtra(RecognizerIntent.EXTRA_PROMPT,"Слушаю…"); startActivityForResult(i,99); status.setText("СЛУШАЮ…"); }catch(Exception e){status.setText("ГОЛОСОВОЙ ВВОД НЕДОСТУПЕН");} }
    @Override protected void onActivityResult(int r,int c,Intent d){super.onActivityResult(r,c,d); if(r==99&&c==RESULT_OK&&d!=null){ArrayList<String>a=d.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS); if(a!=null&&!a.isEmpty()){input.setText(a.get(0)); answer(a.get(0));}}}
    private void answer(String q){ if(q==null||q.trim().isEmpty())return; status.setText("ОБРАБОТКА…"); String out="Принял запрос: "+q; status.setText(out); if(tts!=null)tts.speak(out,TextToSpeech.QUEUE_FLUSH,null,"jarvis"); }
    @Override protected void onDestroy(){ if(tts!=null)tts.shutdown(); super.onDestroy(); }
}
